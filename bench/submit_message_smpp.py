import argparse
# import time
# import socket
import sys
# from threading import Thread
# from Queue import Queue

from smpp.pdu_builder import (
    BindTransceiverResp, BindTransmitterResp, BindReceiverResp,
    EnquireLinkResp, DeliverSM, SubmitSMResp)
from twisted.internet.defer import Deferred, DeferredQueue, inlineCallbacks
from twisted.internet.endpoints import serverFromString
from twisted.internet.protocol import ServerFactory
from twisted.internet.task import react
from vumi.transports.smpp.pdu_utils import seq_no, command_id
from vumi.transports.smpp.tests.fake_smsc import FakeSMSCProtocol


class FakeSMSCFactory(ServerFactory):
    def __init__(self, fake_smsc):
        self.fake_smsc = fake_smsc

    def buildProtocol(self, addr):
        if self.fake_smsc.protocol is not None:
            print "MULTIPLE CONNECTIONS! Please delete extra channels."
            return None
        p = FakeSMSCProtocol(self.fake_smsc)
        self.fake_smsc.protocol = p
        return p


class FakeSMSC(object):
    def __init__(self, reactor, port):
        self.protocol = None
        self.endpoint = serverFromString(reactor, "tcp:%s" % (port,))
        self._lp = None
        self.running = None
        self.bind_queue = DeferredQueue()
        self.unacked = 0
        self.submit_queue = DeferredQueue()

    def start(self):
        assert self._lp is None, "already running"
        print "starting SMSC..."

        def _cb(lp):
            print "SMSC started"
            self._lp = lp
            self.running = Deferred()

        return self.endpoint.listen(FakeSMSCFactory(self)).addCallback(_cb)

    def stop(self):
        assert self._lp is not None, "not running"
        print "stopping SMSC..."

        def _cb(r):
            print "SMSC stopped"
            self._lp = None
            self.running.callback(None)
            self.running = None

        return self._lp.stopListening().addCallback(_cb)

    def send_mo(self, sequence_number, short_message, data_coding=1, **kwargs):
        """
        Send a DeliverSM PDU.
        """
        self.unacked += 1
        return self.send_pdu(
            DeliverSM(
                sequence_number, short_message=short_message,
                data_coding=data_coding, **kwargs))

    def connection_made(self):
        print "ESME connected", self.protocol

    def connection_lost(self):
        print "ESME disconnected", self.protocol
        self.protocol = None

    def send_pdu(self, pdu):
        self.protocol.send_pdu(pdu)

    def pdu_received(self, pdu):
        print "PDU:", pdu
        cmd_id = command_id(pdu)
        if cmd_id.startswith("bind_"):
            return self._bind_resp(pdu)
        if cmd_id == "enquire_link":
            return self._enquire_link_resp(pdu)
        if cmd_id == "deliver_sm_resp":
            self.unacked -= 1
            return
        if cmd_id == "submit_sm":
            self.submit_queue.put(pdu)
            return self._submit_sm_resp(pdu)

    def _bind_resp(self, bind_pdu):
        resp_pdu_classes = {
            'bind_transceiver': BindTransceiverResp,
            'bind_receiver': BindReceiverResp,
            'bind_transmitter': BindTransmitterResp,
        }
        self.assert_command_id(bind_pdu, *resp_pdu_classes)
        resp_pdu_class = resp_pdu_classes.get(command_id(bind_pdu))
        self.send_pdu(resp_pdu_class(seq_no(bind_pdu)))
        self.bind_queue.put(None)

    def _enquire_link_resp(self, enquire_link_pdu):
        self.assert_command_id(enquire_link_pdu, 'enquire_link')
        return self.send_pdu(EnquireLinkResp(seq_no(enquire_link_pdu)))

    def _submit_sm_resp(self, submit_sm_pdu, **kw):
        self.assert_command_id(submit_sm_pdu, 'submit_sm')
        sequence_number = seq_no(submit_sm_pdu)
        message_id = "id%s" % (sequence_number,)
        return self.send_pdu(SubmitSMResp(sequence_number, message_id, **kw))

    def assert_command_id(self, pdu, *command_ids):
        if command_id(pdu) not in command_ids:
            raise ValueError(
                "Expected PDU with command_id in [%s], got %s." % (
                    ", ".join(command_ids), command_id(pdu)))


def parse_arguments(args):
    parser = argparse.ArgumentParser(
        description=(
            'Creates and submits SMS messages via SMPP for benchmarking.'))
    parser.add_argument(
        '--port', dest='port', type=int, default=2775,
        help='Port to listen on')
    parser.add_argument(
        '--start-id', dest='start_id', type=int, default=0,
        help='The integer to start with for sequence numbers')
    parser.add_argument(
        '--end-id', dest='end_id', type=int, default=10000,
        help='The integer to end with for sequence numbers')
    parser.add_argument(
        '--concurrency', dest='concurrency', type=int, default=10,
        help='Maximum number of unacked messages')
    parser.add_argument(
        '--save-file', dest='save_file', default='',
        help='Save output to this file')
    parser.add_argument(
        '--warmup', dest='warmup', default=3000,
        help='Number of iterations to discard for statistics')

    return parser.parse_args(args)


def main(reactor):
    config = parse_arguments(sys.argv[1:])
    return create_requests(
        reactor, config.port, config.start_id, config.end_id,
        config.concurrency, config.save_file, config.warmup)


@inlineCallbacks
def create_requests(reactor, port, start, end, concurrency, save_file, warmup):
    fake_smsc = FakeSMSC(reactor, port)
    yield fake_smsc.start()
    print "Waiting for bind..."
    yield fake_smsc.bind_queue.get()
    print "Bound"
    for i in range(10):
        yield fake_smsc.send_mo(100 + i, "hello %s" % i)
    for i in range(10):
        yield fake_smsc.submit_queue.get()
    yield fake_smsc.stop()

if __name__ == "__main__":
    react(main)

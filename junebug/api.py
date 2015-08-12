import json
from klein import Klein

class JunebugApi(object):
    app = Klein()

    def generate_response(self, request, obj, code=200):
        request.setResponseCode(code)
        request.setHeader('Content-Type', 'application/json')
        return json.dumps(obj)

    @app.handle_errors(Exception)
    def generic_error(self, request, failure):
        request.setResponseCode(500)
        request.setHeader('Content-Type', 'application/json')
        return self.generate_response(request, {
            'code': 500,
            'success': False,
            'error_name': failure.type.__name__,
            'error_description': str(failure.value),
        }, code=500)

    @app.route('/channels', methods=['GET'])
    def get_channel_list(self, request):
        '''List all channels'''
        raise NotImplementedError()

    @app.route('/channels', methods=['POST'])
    def create_channel(self, request):
        '''Create a channel'''
        raise NotImplementedError()

    @app.route('/channels/<string:channel_id>', methods=['GET'])
    def get_channel(self, request, channel_id):
        '''Return the channel configuration and a nested status object'''
        raise NotImplementedError()

    @app.route('/channels/<string:channel_id>', methods=['POST'])
    def modify_channel(self, request, channel_id):
        '''Mondify the channel configuration'''
        raise NotImplementedError()

    @app.route('/channels/<string:channel_id', methods=['DELETE'])
    def delete_channel(self, request, channel_id):
        '''Delete the channel'''
        raise NotImplementedError()

    @app.route('/channels/<string:channel_id>/messages', methods=['POST'])
    def send_message(self, request, channel_id):
        '''Send an outbound (mobile terminated) message'''
        raise NotImplementedError()

    @app.route('/channels/<string:channel_id>/messages/<string:message_id>',
            methods=['GET'])
    def get_message_status(self, request, channel_id, message_id):
        '''Retrieve the status of a message'''
        raise NotImplementedError()

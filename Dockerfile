FROM debian:jessie
MAINTAINER Praekelt Foundation <dev@praekeltfoundation.org>

RUN apt-get -qq update && apt-get -qqy install python-pip python-dev
RUN pip install junebug
RUN mkdir logs

EXPOSE 8080
ENTRYPOINT ["jb", "--config=/app/example-config.yaml"]

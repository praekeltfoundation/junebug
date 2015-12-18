FROM debian:jessie
MAINTAINER Praekelt Foundation <dev@praekeltfoundation.org>

RUN apt-get -qq update && apt-get -qqy install python-pip python-dev
RUN pip install -q junebug

EXPOSE 8080
ENTRYPOINT ["jb", "--config=/app/config.yaml"]

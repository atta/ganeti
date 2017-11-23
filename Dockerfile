FROM ubuntu:16.04
MAINTAINER Ansgar Jazdzewski "ajaz@spreadshirt.net"

RUN apt-get update\
    && apt-get install -y \
               ssh-client \
               rsync \
               git \
               wget \
               gawk \
               curl \
               build-essential \
               debhelper \
               make \
               binutils \
               zlib1g-dev \
               debhelper \
               dh-autoreconf \
               dh-python \
               m4 \
               pep8 \
               pandoc \
               python-all \
               ghc \
               ghc-ghci \
               cabal-install \
               libghc-cabal-dev \
               libghc-case-insensitive-dev \
               libghc-curl-dev \
               libghc-json-dev \
               libghc-snap-server-dev \
               libghc-network-dev \
               libghc-parallel-dev \
               libghc-utf8-string-dev \
               libghc-deepseq-dev \
               libghc-hslogger-dev \
               libghc-crypto-dev \
               libghc-text-dev \
               libghc-hinotify-dev \
               libghc-base64-bytestring-dev \
               libghc-zlib-dev \
               libghc-regex-pcre-dev \
               libghc-attoparsec-dev \
               libghc-vector-dev \
               libghc-lifted-base-dev \
               libghc-lens-dev \
               libghc-psqueue-dev \
               libghc-test-framework-quickcheck2-dev \
               libghc-test-framework-hunit-dev \
               libghc-temporary-dev \
               libghc-old-time-dev \
               libpcre3-dev \
               libcurl4-openssl-dev \
               hlint \
               hscolour \
               python-simplejson \
               python-pyparsing \
               python-openssl \
               python-bitarray \
               python-pyinotify \
               python-pycurl \
               python-paramiko \
               python-ipaddr \
               python-sphinx \
               python-coverage \
               python-pep8 \
               python-mock \
               python-psutil \
               python-yaml \
               graphviz \
               qemu-utils \
               socat \
               bash-completion \
               po-debconf \
    && apt clean\
    && rm -rf /var/lib/apt/lists/*

COPY ./build.sh /build.sh
RUN chmod +x /build.sh
ENTRYPOINT ["/build.sh"]


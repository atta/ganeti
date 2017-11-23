#!/usr/bin/env bash

mkdir -p ./build
mkdir -p ./release

mkdir -p ./build
rm -rf ./build/.*

git clone . build/
cd ./build
git checkout stable-2.16 
cd ..
cp -r ./debian ./build

docker build -t build_ganeti_ubuntu-16.04 .

docker run \
    -v $(pwd)/build:/build \
    -v $(pwd)/release:/release \
    --name ganeti_$(date "+%s") \
    build_ganeti_ubuntu-16.04

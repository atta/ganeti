#!/usr/bin/env bash
mkdir -p ./release/

cd ./build
dpkg-buildpackage -uc -us -b
cp ../*.deb ../release/


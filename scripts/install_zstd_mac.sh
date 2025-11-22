#!/bin/bash

git clone --branch v1.5.7-kernel --single-branch https://github.com/facebook/zstd.git --depth=1
cd zstd
cmake -B ../zstd-lib -S build/cmake -G Ninja -DCMAKE_OSX_ARCHITECTURES="x86_64"
cd ../zstd-lib && ninja
rm -rfd ../zstd

# Alias zstd lib
rm -rfd /usr/local/opt/zstd
mkdir -p /usr/local/opt/zstd
ln -s $PWD/lib /usr/local/opt/zstd

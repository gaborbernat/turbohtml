FROM gcr.io/oss-fuzz-base/base-builder-python
RUN python3 -m pip install --no-cache-dir 'meson>=1.12.1' 'meson-python>=0.22.1' 'ninja>=1.13.2' 'html5lib>=1.1' \
    'markdown-it-py>=4.2' 'tinycss2>=1.5.1' 'typing-extensions>=4.16'
# OSS-Fuzz builds this clone; ClusterFuzzLite replaces it with the checkout under test, so both run the same build.sh
RUN git clone --depth 1 https://github.com/tox-dev/turbohtml $SRC/turbohtml \
    && ln -s $SRC/turbohtml/.clusterfuzzlite/build.sh $SRC/build.sh
WORKDIR $SRC/turbohtml

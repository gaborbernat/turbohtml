FROM gcr.io/oss-fuzz-base/base-builder-python
RUN python3 -m pip install --no-cache-dir 'meson>=1.12.1' 'meson-python>=0.22.1' 'ninja>=1.13.2' 'html5lib>=1.1' \
    'markdown-it-py>=4.2' 'tinycss2>=1.5.1' 'typing-extensions>=4.16'
# ClusterFuzzLite builds this image with the checkout under test as the context and runs compile without touching the
# source, so the image must carry the checkout; an OSS-Fuzz project Dockerfile clones the repository here instead
COPY . $SRC/turbohtml
COPY .clusterfuzzlite/build.sh $SRC/
WORKDIR $SRC/turbohtml

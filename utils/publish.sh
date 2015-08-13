#!/bin/sh -e

rm dist/* || true
python setup.py sdist bdist_wheel
python setup.py register
twine upload dist/*

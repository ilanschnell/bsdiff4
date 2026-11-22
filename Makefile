.PHONY: all build clean mypy test


build:
	python setup.py build_ext --inplace


test: build
	python -c "import bsdiff4; bsdiff4.test()"


mypy:
	mypy bsdiff4/*.py


all: test mypy
	python -m doctest README.rst
	python devel/test_suffix_array.py
	python devel/patch.py


clean:
	rm -rf build dist
	rm -f bsdiff4/*.o bsdiff4/*.so
	rm -rf */__pycache__ *.egg-info
	rm -rf .mypy_cache

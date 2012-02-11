
bsdiff4/core.so: bsdiff4/core.c
	python setup.py build_ext --inplace


test: bsdiff4/core.so
	python -c "import bsdiff4; bsdiff4.test()"


clean:
	rm -rf build dist
	rm -f bsdiff4/*.o bsdiff4/*.so bsdiff4/*.pyc
	rm -rf bsdiff4/__pycache__ *.egg-info

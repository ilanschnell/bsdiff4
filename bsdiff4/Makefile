# This Makefile is only used as an aid for developing.

PYTHON=python


core.so: core.c
	cd .. && ${PYTHON} setup.py build_ext --inplace


clean:
	rm -f *.pyc *.so *.pyd
	rm -rf ../build


test:
	${PYTHON} test_all.py

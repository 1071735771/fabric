==========
Installing
==========

Fabric is best installed via `pip <http://pip-installer.org>`_::

    $ pip install fabric

All advanced ``pip`` use cases work too, such as::

    $ pip install -e git+https://github.com/fabric/fabric

Or cloning the Git repository and running::

    $ pip install -e .

within it.

Your operating system may also have a Fabric package available (though these
are typically older and harder to support), typically called ``fabric`` or
``python-fabric``. E.g.::

    $ sudo apt-get install fabric

Installing Fabric 2.x as ``fabric2``
====================================

Users who are migrating from Fabric 1 to Fabric 2 may find it useful to have
both versions installed side-by-side. The easiest way to do this is to use the
handy ``fabric2`` PyPI entry::

    $ pip install fabric2

This upload is generated from the normal Fabric repository, but is tweaked at
build time so that it installs a ``fabric2`` package instead of a ``fabric``
one. The codebase is otherwise unchanged.

Users working off of the Git repository can enable that same tweak with an
environment variable, e.g.::

    $ PACKAGE_AS_FABRIC2=yes pip install -e .

or::

    $ PACKAGE_AS_FABRIC2=yes python setup.py develop

or any other ``setup.py`` related command.

.. note::
    The value of the environment variable doesn't matter, as long as it is not
    empty.

Dependencies
============

In order for Fabric's installation to succeed, you will need four primary pieces of software:

* the Python programming language;
* the ``setuptools`` packaging/installation library;
* the Python `Paramiko <http://paramiko.org>`_ SSH library;
* and Paramiko's dependency, `Cryptography <https://cryptography.io>`_.

.. TODO: update as appropriate

and, if using the :ref:`parallel execution mode <parallel-execution>`:

* the `multiprocessing`_ library.

Please read on for important details on each dependency -- there are a few
gotchas.

Python
------

Fabric requires `Python <http://python.org>`_ version 2.6+ or 3.3+. Python
versions older than 2.6 are significantly more difficult to support in a dual
Python 2 + Python 3 environment, and will never have support.

setuptools
----------

`Setuptools`_ comes with most Python installations by default; if yours
doesn't, you'll need to grab it. In such situations it's typically packaged as
``python-setuptools``, ``py26-setuptools`` or similar.

.. _setuptools: http://pypi.python.org/pypi/setuptools

``multiprocessing``
-------------------

.. TODO: update parallel stuff

An optional dependency, the ``multiprocessing`` library is included in Python's
standard library in version 2.6 and higher. If you're using Python 2.5 and want
to make use of Fabric's :ref:`parallel execution features <parallel-execution>`
you'll need to install it manually; the recommended route, as usual, is via
``pip``.  Please see the `multiprocessing PyPI page
<http://pypi.python.org/pypi/multiprocessing/>`_ for details.


.. TODO: ditto

.. warning::
    Early versions of Python 2.6 (in our testing, 2.6.0 through 2.6.2) ship
    with a buggy ``multiprocessing`` module that appears to cause Fabric to
    hang at the end of sessions involving large numbers of concurrent hosts.
    If you encounter this problem, either use :ref:`env.pool_size / -z
    <pool-size>` to limit the amount of concurrency, or upgrade to Python
    >=2.6.3.
    
    Python 2.5 is unaffected, as it requires the PyPI version of
    ``multiprocessing``, which is newer than that shipped with Python <2.6.3.

Development dependencies
------------------------

If you are interested in doing development work on Fabric (or even just running
the test suite), you may also need to install some or all of the following
packages:

.. TODO: Update for modern or just nix because, really?

* `git <http://git-scm.com>`_, in order to obtain some of the
  other dependencies below;
* `Nose <https://github.com/nose-devs/nose>`_
* `Coverage <http://nedbatchelder.com/code/modules/coverage.html>`_
* `PyLint <http://www.logilab.org/857>`_
* `Fudge <http://farmdev.com/projects/fudge/index.html>`_
* `Sphinx <http://sphinx.pocoo.org/>`_

For an up-to-date list of exact testing/development requirements, including
version numbers, please see the ``dev-requirements.txt`` file included with the
source distribution. This file is intended to be used with ``pip``, e.g. ``pip
install -r dev-requirements.txt``.


.. _downloads:

Downloads
=========

To obtain a tar.gz or zip archive of the Fabric source code, you may visit
`Fabric's PyPI page <http://pypi.python.org/pypi/Fabric>`_, which offers manual
downloads in addition to being the entry point for ``pip`` and
``easy-install``.


.. _source-code-checkouts:

Source code checkouts
=====================

The Fabric developers manage the project's source code with the `Git
<http://git-scm.com>`_ DVCS. To follow Fabric's development via Git instead of
downloading official releases, you have the following options:

* Clone the canonical repository straight from `the Fabric organization's
  repository on Github <https://github.com/fabric/fabric>`_ (cloning
  instructions available on that page).
* Make your own fork of the Github repository by making a Github account,
  visiting `fabric/fabric <http://github.com/fabric/fabric>`_ and clicking the
  "fork" button.

.. note::

    If you've obtained the Fabric source via source control and plan on
    updating your checkout in the future, we highly suggest using ``pip install
    -e .`` (or ``python setup.py develop``) instead -- it will use symbolic
    links instead of file copies, ensuring that imports of the library or use
    of the command-line tool will always refer to your checkout.

For information on the hows and whys of Fabric development, including which
branches may be of interest and how you can help out, please see the
:doc:`development` page.


.. _pypm:

ActivePython and PyPM
=====================

.. TODO: update example output for fab 2 versions

Windows users who already have ActiveState's `ActivePython
<http://www.activestate.com/activepython/downloads>`_ distribution installed
may find Fabric is best installed with `its package manager, PyPM
<http://code.activestate.com/pypm/>`_. Below is example output from an
installation of Fabric via ``pypm``::

    C:\> pypm install fabric
    The following packages will be installed into "%APPDATA%\Python" (2.7):
     paramiko-1.7.8 pycrypto-2.4 fabric-1.3.0
    Get: [pypm-free.activestate.com] fabric 1.3.0
    Get: [pypm-free.activestate.com] paramiko 1.7.8
    Get: [pypm-free.activestate.com] pycrypto 2.4
    Installing paramiko-1.7.8
    Installing pycrypto-2.4
    Installing fabric-1.3.0
    Fixing script %APPDATA%\Python\Scripts\fab-script.py
    C:\>

======================
Command-line interface
======================

This page documents the details of Fabric's optional command-line interface,
``fab``.


Options & arguments
===================

.. option:: -F, --ssh-config

    Takes a path to load as a runtime SSH config file. See :ref:`ssh-config`.

.. option:: -H, --hosts

    Takes a comma-separated string listing hostnames against which tasks
    should be executed, in serial. See :ref:`runtime-hosts`.


Seeking & loading tasks
=======================

``fab`` follows all the same rules as Invoke's :ref:`collection loading
<collection-discovery>`, with the sole exception that the default collection
name sought is ``fabfile`` instead of ``tasks``. Thus, whenever Invoke's
documentation mentions ``tasks`` or ``tasks.py``, Fabric substitutes
``fabfile`` / ``fabfile.py``.

For example, if your current working directory is
``/home/myuser/projects/mywebapp``, running ``fab --list`` will cause Fabric to
look for ``/home/myuser/projects/mywebapp/fabfile.py`` (or
``/home/myuser/projects/mywebapp/fabfile/__init__.py`` - Python's import system
treats both the same). If it's not found there,
``/home/myuser/projects/fabfile.py`` is sought next; and so forth.


.. _runtime-hosts:

Runtime specification of host lists
===================================

While advanced use cases may need to take matters into their own hands, you can
go reasonably far with the core :option:`--hosts` flag, which specifies one or
more hosts the given task(s) should execute against.

By default, execution is a serial process: for each task on the command line,
run it once for each host given to :option:`--hosts`. Imagine tasks that simply
print ``Running <task name> on <host>!``::

    $ fab --hosts host1,host2,host3 taskA taskB
    Running taskA on host1!
    Running taskA on host2!
    Running taskA on host3!
    Running taskB on host1!
    Running taskB on host2!
    Running taskB on host3!

.. note::
    When :option:`--hosts` is not given, ``fab`` behaves similarly to Invoke's
    :ref:`command-line interface <inv>`, generating regular instances of
    `~invoke.context.Context` instead of `Connections <.Connection>`.

Executing arbitrary/ad-hoc commands
===================================

``fab`` leverages a lesser-known command line convention and may be called in
the following manner::

    $ fab [options] -- [shell command]

where everything after the ``--`` is turned into a temporary `.Connection.run`
call, and is not parsed for ``fab`` options. If you've specified a host list
via an earlier task or the core CLI flags, this usage will act like a one-line
anonymous task.

For example, let's say you wanted kernel info for a bunch of systems::

    $ fab -H host1,host2,host3 -- uname -a

Such a command is equivalent to the following Fabric library code::

    from fabric import Group

    Group('host1', 'host2', 'host3').run("uname -a")

Most of the time you will want to just write out the task in your fabfile
(anything you use once, you're likely to use again) but this feature provides a
handy, fast way to dash off an SSH-borne command while leveraging predefined
connection settings.

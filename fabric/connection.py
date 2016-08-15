from contextlib import contextmanager
from threading import Thread, Event
import errno
import select
import socket

from invoke import Context
from invoke.config import Config as InvokeConfig, merge_dicts
from invoke.vendor import six
from paramiko.client import SSHClient, AutoAddPolicy
from paramiko.config import SSHConfig
from paramiko.proxy import ProxyCommand

from .runners import Remote
from .transfer import Transfer
from .tunnels import Listener, Tunnel
from .util import get_local_user


class Config(InvokeConfig):
    """
    An `invoke.config.Config` subclass with extra Fabric-related defaults.

    This class behaves like `invoke.config.Config` in every way, save for that
    its `~invoke.config.Config.global_defaults` staticmethod has been extended
    to add Fabric-specific settings such as user and port number.

    Intended for use with `.Connection`, as using vanilla
    `invoke.config.Config` objects would require you to manually define
    ``port``, ``user`` and so forth .
    """
    # NOTE: docs for these are kept in sites/docs/api/connection.rst for
    # tighter control over value display (avoids baking docs-building user's
    # username into the docs).
    @staticmethod
    def global_defaults():
        defaults = InvokeConfig.global_defaults()
        ours = {
            'port': 22,
            'user': get_local_user(),
        }
        merge_dicts(defaults, ours)
        return defaults


class Connection(Context):
    """
    A connection to an SSH daemon, with methods for commands and file transfer.

    This class inherits from Invoke's `~invoke.context.Context`, as it is a
    context within which commands, tasks etc can operate. It also encapsulates
    a Paramiko `~paramiko.client.SSHClient` instance, performing useful high
    level operations with that `~paramiko.client.SSHClient` and
    `~paramiko.channel.Channel` instances generated from it.

    `.Connection` has a basic "`create <__init__>`, `connect/open <open>`, `do
    work <run>`, `disconnect/close <close>`" lifecycle:

    * `Instantiation <__init__>` imprints the object with its connection
      parameters (but does **not** actually initiate the network connection).
    * Methods like `run`, `get` etc automatically trigger a call to
      `open` if the connection is not active; users may of course call `open`
      manually if desired.
    * Connections do not always need to be explicitly closed; much of the
      time, Paramiko's garbage collection hooks or Python's own shutdown
      sequence will take care of things. **However**, should you encounter edge
      cases (for example, sessions hanging on exit) it's helpful to explicitly
      close connections when you're done with them.

      This can be accomplished by manually calling `close`, or by using the
      object as a contextmanager::

        with Connection('host') as cxn:
            cxn.run('command')
            cxn.put('file')

    .. note::
        This class rebinds `invoke.context.Context.run` to `.local` so both
        remote and local command execution can coexist.
    """
    # TODO: should "reopening" an existing Connection object that has been
    # closed, be allowed? (See e.g. how v1 detects closed/semi-closed
    # connections & nukes them before creating a new client to the same host.)
    # TODO: push some of this into paramiko.client.Client? e.g. expand what
    # Client.exec_command does, it already allows configuring a subset of what
    # we do / will eventually do / did in 1.x. It's silly to have to do
    # .get_transport().open_session().
    def __init__(
        self,
        host,
        user=None,
        port=None,
        key_filename=None,
        config=None,
        gateway=None
    ):
        """
        Set up a new object representing a server connection.

        :param str host:
            the hostname (or IP address) of this connection.

            May include shorthand for the ``user`` and/or ``port`` parameters,
            of the form ``user@host``, ``host:port``, or ``user@host:port``.

            .. note::
                Due to ambiguity, IPv6 host addresses are incompatible with the
                ``host:port`` shorthand (though ``user@host`` will still work
                OK). In other words, the presence of >1 ``:`` character will
                prevent any attempt to derive a shorthand port number; use the
                explicit ``port`` parameter instead.

        :param str user:
            the login user for the remote connection. Defaults to
            ``config.user``.

        :param int port:
            the remote port. Defaults to ``config.port``.

        :param str key_filename:
            a string or list of strings specifying SSH key paths to load.

            Passed directly to `paramiko.client.SSHClient.connect`. Default:
            ``None``.

        :param fabric.connection.Config config:
            configuration settings to use when executing methods on this
            `.Connection` (e.g. default SSH port and so forth).

            Default is an anonymous `.Config` object.

        :param gateway:
            An object to use as a proxy or gateway for this connection.

            This parameter accepts one of the following:

            - another `.Connection` (for a ``direct-tcpip`` gateway);
            - a shell command string as a `str` or `unicode` (for a
              ``ProxyCommand`` gateway).

            Default: ``None``, in which case no gatewaying will occur.

            .. seealso:: :ref:`ssh-gateways`

        :raises exceptions.ValueError:
            if user or port values are given via both ``host`` shorthand *and*
            their own arguments. (We `refuse the temptation to guess`_).

        .. _refuse the temptation to guess:
            http://zen-of-python.info/
            in-the-face-of-ambiguity-refuse-the-temptation-to-guess.html#12
        """
        # NOTE: for now, we don't call our parent __init__, since all it does
        # is set a default config (to Invoke's Config, not ours). If
        # invoke.Context grows more behavior later we may need to change this.

        # TODO: how does this config mesh with the one from us being an Invoke
        # context, for keys not part of the defaults? Do we namespace all our
        # stuff or just overlay it? Starting with overlay, but...

        #: The .Config object referenced when handling default values (for e.g.
        #: user or port, when not explicitly given) or deciding how to behave.
        self.config = config if config is not None else Config()
        # TODO: when/how to run load_files, merge, load_shell_env, etc?
        # TODO: i.e. what is the lib use case here (and honestly in invoke too)

        shorthand = self.derive_shorthand(host)
        host = shorthand['host']
        err = "You supplied the {0} via both shorthand and kwarg! Please pick one." # noqa
        if shorthand['user'] is not None:
            if user is not None:
                raise ValueError(err.format('user'))
            user = shorthand['user']
        if shorthand['port'] is not None:
            if port is not None:
                raise ValueError(err.format('port'))
            port = shorthand['port']

        #: The hostname of the target server.
        self.host = host
        #: The username this connection will use to connect to the remote end.
        self.user = user or self.config.user
        #: The network port to connect on.
        self.port = port or self.config.port
        #: Specified key filename(s) used for authentication.
        self.key_filename = key_filename
        #: The gateway `.Connection` or ``ProxyCommand`` string to be used,
        #: if any.
        self.gateway = gateway
        # NOTE: we use string above, vs ProxyCommand obj, to avoid spinning up
        # the ProxyCommand subprocess at init time, vs open() time.
        # TODO: make paramiko.proxy.ProxyCommand lazy instead?

        #: The `paramiko.client.SSHClient` instance this connection wraps.
        client = SSHClient()
        client.set_missing_host_key_policy(AutoAddPolicy())
        self.client = client

        #: A convenience handle onto the return value of
        #: ``self.client.get_transport()``.
        self.transport = None

    def __str__(self):
        bits = [('id', id(self))]
        if self.user != self.config.user:
            bits.append(('user', repr(self.user)))
        bits.append(('host', repr(self.host)))
        if self.port != self.config.port:
            bits.append(('port', repr(self.port)))
        if self.gateway:
            # Displaying type because gw params would probs be too verbose
            val = 'direct-tcpip'
            if isinstance(self.gateway, six.string_types):
                val = 'proxy'
            bits.append(('gw', val))
        return "<Connection {0}>".format(
            " ".join("{0}={1}".format(*x) for x in bits)
        )

    def derive_shorthand(self, host_string):
        user_hostport = host_string.rsplit('@', 1)
        hostport = user_hostport.pop()
        user = user_hostport[0] if user_hostport and user_hostport[0] else None

        # IPv6: can't reliably tell where addr ends and port begins, so don't
        # try (and don't bother adding special syntax either, user should avoid
        # this situation by using port=).
        if hostport.count(':') > 1:
            host = hostport
            port = None
        # IPv4: can split on ':' reliably.
        else:
            host_port = hostport.rsplit(':', 1)
            host = host_port.pop(0) or None
            port = host_port[0] if host_port and host_port[0] else None

        if port is not None:
            port = int(port)

        return {'user': user, 'host': host, 'port': port}

    @property
    def host_string(self):
        # TODO: remove this ASAP once a better way of representing connections
        # in aggregate results is found! (E.g. including local port or other
        # truly-differentiating data)
        # TODO: or at least rename/doc it so it's obvious it's just a
        # convenient identifier & not something used instead of an actual
        # Connection object.
        return "{0}@{1}:{2}".format(self.user, self.host, self.port)

    @property
    def is_connected(self):
        """
        Whether or not this connection is actually open.
        """
        return self.transport.active if self.transport else False

    def open(self):
        """
        Initiate an SSH connection to the host/port this object is bound to.

        This may include activating the configured gateway connection, if one
        is set.

        Also saves a handle to the now-set Transport object for easier access.
        """
        if not self.is_connected:
            # TODO: work in all the stuff Fabric 1 supports here & maybe some
            # it doesn't.
            # TODO: and if possible, make it easy for users to arbitrarily
            # submit kwargs so we don't have to constantly manage kwarg parity
            # for stuff that otherwise doesn't need any dev on our side. (Think
            # things like timeouts, Kerberos kwargs, etc.)
            # TODO: and that methodology should ideally work with the config
            # system somehow, even if it's e.g.
            # config.fabric.extra_connection_kwargs or something.
            kwargs = dict(
                username=self.user,
                hostname=self.host,
                port=self.port,
            )
            if self.gateway:
                kwargs['sock'] = self.open_gateway()
            if self.key_filename:
                kwargs['key_filename'] = self.key_filename
            self.client.connect(**kwargs)
            self.transport = self.client.get_transport()

    def open_gateway(self):
        """
        Obtain a socket-like object from `gateway`.

        :returns:
            A ``direct-tcpip`` `paramiko.channel.Channel`, if `gateway` was a
            `.Connection`; or a `~paramiko.proxy.ProxyCommand`, if `gateway`
            was a `str` or `unicode`.
        """
        # ProxyCommand is faster to set up, so do it first.
        if isinstance(self.gateway, six.string_types):
            # Leverage a dummy SSHConfig to ensure %h/%p/etc are parsed.
            # TODO: use real SSH config once loading one properly is
            # implemented.
            ssh_conf = SSHConfig()
            dummy = "Host {0}\n    ProxyCommand {1}"
            ssh_conf.parse(six.StringIO(dummy.format(self.host, self.gateway)))
            return ProxyCommand(ssh_conf.lookup(self.host)['proxycommand'])
        # Handle inner-Connection gateway type here.
        # TODO: logging
        self.gateway.open()
        # TODO: expose the opened channel itself as an attribute? (another
        # possible argument for separating the two gateway types...) e.g. if
        # someone wanted to piggyback on it for other same-interpreter socket
        # needs...
        # TODO: and the inverse? allow users to supply their own socket/like
        # object they got via $WHEREEVER?
        # TODO: how best to expose timeout param? reuse general connection
        # timeout from config?
        return self.gateway.transport.open_channel(
            kind='direct-tcpip',
            dest_addr=(self.host, int(self.port)),
            # NOTE: src_addr needs to be 'empty but not None' values to
            # correctly encode into a network message. Theoretically Paramiko
            # could auto-interpret None sometime & save us the trouble.
            src_addr=('', 0),
        )

    def close(self):
        """
        Terminate the network connection to the remote end, if open.

        If no connection is open, this method does nothing.
        """
        if self.is_connected:
            self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _create_session(self):
        self.open()
        return self.transport.open_session()

    def run(self, command, **kwargs):
        """
        Execute a shell command on the remote end of this connection.

        This method wraps an SSH-capable implementation of
        `invoke.runners.Runner.run`; see its docs for details.
        """
        self.open()
        return Remote(context=self).run(command, **kwargs)

    def sudo(self, command, **kwargs):
        """
        Execute a shell command, via ``sudo``, on the remote end.

        This method is identical to `invoke.context.Context.sudo` in every way,
        except in that -- like `run` -- it honors per-host/per-connection
        configuration overrides in addition to the generic/global ones. Thus,
        for example, per-host sudo passwords may be configured.
        """
        # TODO: we may never actually need to tweak the implementation, in
        # which case we want to...just touch Remote.sudo.__doc__ or something?
        # Move the above to the API doc shim page? (Will that even render
        # inherited-only methods?)
        super(Connection, self).sudo(command, **kwargs)

    def local(self, *args, **kwargs):
        """
        Execute a shell command on the local system.

        This method is a straight wrapper of `invoke.run`; see its docs for
        details and call signature.
        """
        return super(Connection, self).run(*args, **kwargs)

    def sftp(self):
        """
        Return a `~paramiko.sftp_client.SFTPClient` object.

        If called more than one time, memoizes the first result; thus, any
        given `.Connection` instance will only ever have a single SFTP client,
        and state (such as that managed by
        `~paramiko.sftp_client.SFTPClient.chdir`) will be preserved.
        """
        self.open()
        if not hasattr(self, '_sftp'):
            self._sftp = self.client.open_sftp()
        return self._sftp

    def get(self, *args, **kwargs):
        """
        Get a remote file to the local filesystem or file-like object.

        Simply a wrapper for `.Transfer.get`. Please see its documentation for
        all details.
        """
        return Transfer(self).get(*args, **kwargs)

    def put(self, *args, **kwargs):
        """
        Put a remote file (or file-like object) to the remote filesystem.

        Simply a wrapper for `.Transfer.put`. Please see its documentation for
        all details.
        """
        return Transfer(self).put(*args, **kwargs)

    # TODO: finalize API names/nomenclature, "forwarding" is really confusing
    # always, how best to mitigate that exactly?
    # TODO: clean up docstrings
    # TODO: yield the socket for advanced users? Other advanced use cases
    # (perhaps factor out socket creation itself)?
    # TODO: probably push some of this down into Paramiko
    @contextmanager
    def forward_local(self, local_port, remote_port=None,
        remote_host='localhost', local_host='localhost'):
        """
        Open a tunnel connecting ``local_port`` to the server's environment.

        For example, say you want to connect to a remote PostgreSQL database
        which is locked down and only accessible via the system it's running
        on. You have SSH access to this server, so you can temporarily make
        port 5432 on your local system act like port 5432 on the server::

            import psycopg2
            from fabric import Connection

            with Connection('my-db-server').forward_local(5432):
                db = psycopg2.connect(
                    host='localhost', port=5432, database='mydb'
                )
                # Do things with 'db' here

        This method is analogous to using the ``-L`` option of OpenSSH's
        ``ssh`` program.

        :param int local_port: The local port number on which to listen.

        :param str local_host:
            The local hostname/interface on which to listen. Default:
            ``localhost``.

        :param int remote_port:
            The remote port number. Defaults to the same value as
            ``local_port``.

        :param str remote_host:
            The remote hostname serving the forwarded remote port. Default:
            ``localhost`` (i.e., the host this `.Connection` is connected to.)

        :returns:
            Nothing; this method is only useful as a context manager affecting
            local operating system state.
        """
        self.open()
        if not remote_port:
            remote_port = local_port

        # Listener does all of the work, sitting in the background (so we can
        # yield) and spawning threads every time somebody connects to our local
        # port.
        # TODO: rename to something like TunnelManager?
        finished = Event()
        listener = Listener(
            local_port=local_port, local_host=local_host,
            remote_port=remote_port, remote_host=remote_host,
            # TODO: not a huge fan of handing in our transport, but...?
            transport=self.transport, finished=finished,
        )
        listener.start()

        # Return control to caller now that things ought to be operational
        try:
            yield
        # Teardown once user exits block
        finally:
            # Signal to listener that it should close all open tunnels
            finished.set()
            # Then wait for it to do so
            listener.join()
            # TODO: raise any errors encountered inside thread
            # TODO: cancel port forward on transport? Does that even make sense
            # here (where we used direct-tcpip) vs the opposite method (which
            # is what uses forward-tcpip)?

    def forward_remote(self, xxx):
        pass


class Group(list):
    """
    A collection of `.Connection` objects whose API operates on its contents.
    """
    def __init__(self, hosts=None):
        """
        Create a group of connections from an iterable of shorthand strings.

        See `.Connection` for details on the format of these strings - they
        will be used as the first positional argument of `.Connection`
        constructors.
        """
        # TODO: allow splat-args form in addition to iterable arg?
        # TODO: #563, #388 (could be here or higher up in Program area)
        if hosts:
            self.extend(map(Connection, hosts))

    @classmethod
    def from_connections(cls, connections):
        """
        Alternate constructor accepting `.Connection` objects.
        """
        group = cls()
        group.extend(connections)
        return group

    def run(self, *args, **kwargs):
        # TODO: how to change method of execution across contents? subclass,
        # kwargs, additional methods, inject an executor?
        # TODO: retval needs to be host objects or something non-string. See
        # how tutorial mentions 'ResultSet' - useful to construct or no?
        # TODO: also need way to deal with duplicate connections (see THOUGHTS)
        result = {}
        for cxn in self:
            result[cxn.host_string] = cxn.run(*args, **kwargs)
        return result

    # TODO: mirror Connection's close()?

    # TODO: execute() as mentioned in tutorial

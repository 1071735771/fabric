from invoke.vendor.six import StringIO

from spec import Spec, ok_, eq_
from invoke import pty_size, Result

from fabric.connection import Connection
from fabric.runners import Remote

from _util import mock_remote, Session


# On most systems this will explode if actually executed as a shell command;
# this lets us detect holes in our network mocking.
CMD = "nope"


class Remote_(Spec):
    def needs_handle_on_a_Connection(self):
        c = Connection('host')
        ok_(Remote(context=c).context is c)

    class run:
        @mock_remote
        def calls_expected_paramiko_bits(self, chan):
            c = Connection('host')
            r = Remote(context=c)
            r.run(CMD)
            # mock_remote makes generic sanity checks like "were
            # get_transport and open_session called", but we also want to make
            # sure that exec_command got run with our arg to run().
            chan.exec_command.assert_called_with(CMD)

        @mock_remote(Session(out=b"hello yes this is dog"))
        def writes_remote_streams_to_local_streams(self, chan):
            c = Connection('host')
            r = Remote(context=c)
            fakeout = StringIO()
            r.run(CMD, out_stream=fakeout)
            eq_(fakeout.getvalue(), "hello yes this is dog")

        @mock_remote
        def pty_True_uses_paramiko_get_pty(self, chan):
            c = Connection('host')
            r = Remote(context=c)
            r.run(CMD, pty=True)
            cols, rows = pty_size()
            chan.get_pty.assert_called_with(width=cols, height=rows)

        @mock_remote
        def return_value_is_Result_subclass_exposing_cxn_used(self, chan):
            c = Connection('host')
            r = Remote(context=c)
            result = r.run(CMD)
            ok_(isinstance(result, Result))
            # Mild sanity test for other Result superclass bits
            eq_(result.ok, True)
            eq_(result.exited, 0)
            # Test the attr our own subclass adds
            ok_(result.connection is c)

        @mock_remote
        def channel_is_closed_normally(self, chan):
            # I.e. Remote.stop() closes the channel automatically
            r = Remote(context=Connection('host'))
            r.run(CMD)
            chan.close.assert_called_once_with()

        @mock_remote
        def channel_is_closed_on_body_exceptions(self, chan):
            # I.e. Remote.stop() is called within a try/finally.
            # Technically is just testing invoke.Runner, but meh.
            class Oops(Exception):
                pass
            class _OopsRemote(Remote):
                def wait(self):
                    raise Oops()
            r = _OopsRemote(context=Connection('host'))
            try:
                r.run(CMD)
            except Oops:
                chan.close.assert_called_once_with()
            else:
                assert False, "Runner failed to raise exception!"

        def channel_close_skipped_when_channel_not_even_made(self):
            # I.e. if obtaining self.channel doesn't even happen (i.e. if
            # Connection.create_session() dies), we need to account for that
            # case...
            class Oops(Exception):
                pass
            def oops():
                raise Oops
            cxn = Connection('host')
            cxn.create_session = oops
            r = Remote(context=cxn)
            # When bug present, this will result in AttributeError because
            # Remote has no 'channel'
            try:
                r.run(CMD)
            except Oops:
                pass
            else:
                assert False, "Weird, Oops never got raised..."

        # TODO: how much of Invoke's tests re: the upper level run() (re:
        # things like returning Result, behavior of Result, etc) to
        # duplicate here? Ideally none or very few core ones.

        # TODO: only test guts of our stuff, Invoke's Runner tests should
        # handle all the normal shit like stdout/err print and capture.
        # Implies we want a way to import & run those tests ourselves, though,
        # with the Runner instead being a Remote. Or do we just replicate the
        # basics?

        # TODO: all other run() tests from fab1...


class RemoteSudo_(Spec):
    # * wrapper/preparation method now adds sudo wrapper too
    # * works well with bash/etc wrapping
    # * can auto-respond with password
    # * prompts terminal (mock?) if no stored password
    # * stored password works on per connection object basis (talks to
    #   connection/context?)
    pass

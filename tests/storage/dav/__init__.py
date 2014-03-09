
# -*- coding: utf-8 -*-
'''
    vdirsyncer.tests.storage.dav
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Using an actual CalDAV/CardDAV server to test the CalDAV and CardDAV
    storages. Done by using Werkzeug's test client for WSGI apps. While this is
    pretty fast, Radicale has so much global state such that a clean separation
    of the unit tests is not easy.

    :copyright: (c) 2014 Markus Unterwaditzer
    :license: MIT, see LICENSE for more details.
'''

import sys
import os
import urlparse
import pytest
import mock

from werkzeug.test import Client
from werkzeug.wrappers import BaseResponse as WerkzeugResponse

from .. import StorageTests
import vdirsyncer.exceptions as exceptions
from vdirsyncer.storage.base import Item


def do_the_radicale_dance(tmpdir):
    # All of radicale is already global state, the cleanliness of the code and
    # all hope is already lost. This function runs before every test.

    # This wipes out the radicale modules, to reset all of its state.
    for module in list(sys.modules):
        if module.startswith('radicale'):
            del sys.modules[module]

    # radicale.config looks for this envvar. We have to delete it before it
    # tries to load a config file.
    os.environ['RADICALE_CONFIG'] = ''
    import radicale.config

    # Now we can set some basic configuration.
    radicale.config.set('storage', 'type', 'filesystem')
    radicale.config.set('storage', 'filesystem_folder', tmpdir)
    radicale.config.set('rights', 'type', 'None')

    # This one is particularly useful with radicale's debugging logs and
    # pytest-capturelog, however, it is very verbose.
    #import radicale.log
    #radicale.log.start()


class Response(object):

    '''Fake API of requests module'''

    def __init__(self, x):
        self.x = x
        self.status_code = x.status_code
        self.content = x.get_data(as_text=False)
        self.headers = x.headers
        self.encoding = x.charset

    def raise_for_status(self):
        '''copied from requests itself'''
        if 400 <= self.status_code < 600:
            from requests.exceptions import HTTPError
            raise HTTPError(str(self.status_code))


@pytest.mark.usefixtures('class_tmpdir')
class DavStorageTests(StorageTests):
    '''hrefs are paths without scheme or netloc'''
    storage_class = None
    radicale_path = None
    patcher = None

    def _get_storage(self, **kwargs):
        do_the_radicale_dance(self.tmpdir)
        from radicale import Application
        app = Application()

        c = Client(app, WerkzeugResponse)
        server = 'http://127.0.0.1'
        full_url = server + self.radicale_path

        def x(session, method, url, data=None, headers=None, **kw):
            path = urlparse.urlparse(url).path or self.radicale_path
            assert isinstance(data, bytes) or data is None
            r = c.open(path=path, method=method, data=data, headers=headers)
            r = Response(r)
            return r

        self.patcher = p = mock.patch('requests.Session.request', new=x)
        p.start()

        return self.storage_class(url=full_url, **kwargs)

    def teardown_method(self, method):
        self.app = None
        if self.patcher is not None:
            self.patcher.stop()
            self.patcher = None

    def test_dav_broken_item(self):
        item = Item(u'UID:1')
        s = self._get_storage()
        try:
            s.upload(item)
        except exceptions.Error:
            pass
        assert not list(s.list())

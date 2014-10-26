#! /usr/bin/env python
# -*- coding: utf-8 -*-
# vim:fenc=utf-8
#
# Copyright © 2014 uralbash <root@uralbash.ru>
#
# Distributed under terms of the MIT license.

"""
Test for sacrud.common
"""

import os
import unittest

import transaction
from pyramid import testing
from pyramid.httpexceptions import HTTPNotFound

from pyramid_sacrud.breadcrumbs import breadcrumbs, get_crumb
from pyramid_sacrud.common import get_obj_from_settings
from pyramid_sacrud.tests import (DB_FILE, Profile,
                                  TEST_DATABASE_CONNECTION_STRING, User)
from pyramid_sacrud.views.CRUD import (CRUD, get_table, pk_list_to_dict,
                                       update_difference_object)

from .test_models import _initTestingDB, user_add


class BaseTest(unittest.TestCase):

    def setUp(self):
        from pyramid_sacrud.tests.mock_main import main
        settings = {'sqlalchemy.url': TEST_DATABASE_CONNECTION_STRING}
        app = main({}, **settings)
        DBSession = _initTestingDB()
        self.DBSession = DBSession
        self.user_1 = user_add(DBSession)
        self.user_2 = user_add(DBSession)

        from webtest import TestApp
        self.testapp = TestApp(app)

    def tearDown(self):
        del self.testapp
        from pyramid_sacrud.tests import DBSession
        DBSession.remove()
        DBSession.close()
        transaction.commit()
        os.remove(DB_FILE)


class BreadCrumbsTest(unittest.TestCase):

    def test_get_crumb(self):
        crumb = get_crumb('Dashboard', True, 'sa_home', {'name': 'foo'})
        self.assertEqual(crumb, {'visible': True, 'name': 'Dashboard',
                                 'param': {'name': 'foo'},
                                 'view': 'sa_home'})

    def test_breadcrumbs(self):
        bc = breadcrumbs('foo', 'ffoo', 'sa_list')
        self.assertEqual(bc,
                         [{'visible': True, 'name': u'Dashboard',
                           'param': {'name': 'foo'},
                           'view': 'sa_home'},
                          {'visible': True, 'name': 'ffoo',
                           'param': {'name': 'foo'}, 'view': 'sa_list'}])

        bc = breadcrumbs('foo', 'barr', 'sa_create')
        self.assertEqual(bc, [{'visible': True, 'name': 'Dashboard',
                               'param': {'name': 'foo'}, 'view': 'sa_home'},
                              {'visible': True, 'name': 'barr',
                               'param': {'name': 'foo'}, 'view': 'sa_list'},
                              {'visible': False, 'name': 'create',
                               'param': {'name': 'foo'}, 'view': 'sa_list'}])

        bc = breadcrumbs('foo', 'bazz', 'sa_read')
        self.assertEqual(bc, [{'visible': True, 'name': 'Dashboard',
                               'param': {'name': 'foo'}, 'view': 'sa_home'},
                              {'visible': True, 'name': 'bazz',
                               'param': {'name': 'foo'}, 'view': 'sa_list'},
                              {'visible': False, 'name': None,
                               'param': {'name': 'foo'}, 'view': 'sa_list'}])


class CommonTest(unittest.TestCase):

    def test_get_obj_from_settings(self):
        request = testing.DummyRequest()
        config = testing.setUp(request=request)
        config.registry.settings['foo.User'] = 'pyramid_sacrud.tests:User'
        obj = get_obj_from_settings(request, 'foo.User')
        self.assertEqual(obj, User)

        config.registry.settings['foo.User'] = User
        obj = get_obj_from_settings(request, 'foo.User')
        self.assertEqual(obj, User)


class CommonCrudTest(BaseTest):

    # TODO: may be this need move to common
    def test_update_difference_object(self):
        class Foo: pass
        obj = Foo()
        update_difference_object(obj, "foo", "bar")
        self.assertEqual(obj.foo, "bar")

        obj = {}
        update_difference_object(obj, "foo", "bar")
        self.assertEqual(obj["foo"], "bar")

    def test_pk_list_to_dict(self):
        foo = [1, 2, 3, "a", "b", {"foo": "bar"}]
        resp = pk_list_to_dict(foo)
        self.assertEqual(resp, {1: 2, 3: 'a', 'b': {'foo': 'bar'}})

        foo = [1, 2, 3, "a", "b"]
        resp = pk_list_to_dict(foo)
        self.assertEqual(resp, None)


class ViewPageTest(BaseTest):

    def _include_sacrud(self):
        request = testing.DummyRequest()
        config = testing.setUp(request=request)

        config.registry.settings['sqlalchemy.url'] = TEST_DATABASE_CONNECTION_STRING
        config.include('pyramid_sacrud', route_prefix='/admin')
        settings = config.registry.settings
        settings['pyramid_sacrud.models'] = {'': {'tables': [User]},
                                             'Auth models': {'tables': [User, Profile]}
                                             }
        return request

    def test_bad_pk_init(self):
        request = self._include_sacrud()
        request.matchdict["pk"] = ("foo", "bar", "baz")  # bad pk's
        request.matchdict["table"] = "user"
        with self.assertRaises(HTTPNotFound) as cm:
            CRUD(request)
        the_exception = str(cm.exception)
        self.assertEqual(the_exception, 'The resource could not be found.')

    def test_bad_table_init(self):
        request = self._include_sacrud()
        request.matchdict["pk"] = ("foo", "bar")
        request.matchdict["table"] = "user666"
        with self.assertRaises(HTTPNotFound) as cm:
            CRUD(request)
        the_exception = str(cm.exception)
        self.assertEqual(the_exception, 'The resource could not be found.')

    def test_get_table(self):
        request = self._include_sacrud()
        user = get_table('UsEr', request)
        self.assertEqual(user, User)
        foo = get_table('foo', request)
        self.assertEqual(foo, None)

    def test_sa_home(self):
        res = self.testapp.get('/admin/', status=200)
        self.failUnless('Auth models' in str(res.body))
        self.failUnless('user' in str(res.body))
        self.failUnless('profile' in str(res.body))

    def test_sa_list(self):
        res = self.testapp.get('/admin/user/', status=200)
        self.failUnless("user_[&#39;id&#39;, 2]" in str(res.body))
        res = self.testapp.get('/admin/profile/', status=200)
        self.failUnless("profile_[&#39;id&#39;, 1]" not in str(res.body))

    def test_sa_list_delete_actions(self):
        items_list = [u'["id", %s]' % self.user_1,
                      u'["id", %s]' % self.user_2]
        self.testapp.post('/admin/user/',
                          {'selected_action': 'delete',
                           'selected_item': items_list},
                          status=200)
        transaction.commit()
        count = self.DBSession.query(User).filter(
            User.id.in_([self.user_1, self.user_2])).count()
        self.assertEqual(count, 0)

    def test_sa_update_get(self):
        res = self.testapp.get('/admin/user/update/id/%s/' % self.user_1,
                               status=200)
        self.failUnless('Delete' in str(res.body))

    def test_sa_update_post(self):
        self.testapp.post('/admin/user/update/id/%s/' % self.user_1,
                          {'form.submitted': '1',
                           'name': 'foo bar'},
                          status=302)
        user = self.DBSession.query(User).get(self.user_1)
        self.assertEqual(user.name, 'foo bar')

    def test_sa_create(self):
        res = self.testapp.get('/admin/user/create/', status=200)
        self.failUnless('create' in str(res.body))

    def test_sa_create_post(self):
        self.testapp.post('/admin/user/create/',
                          {'form.submitted': '1',
                           'name': 'foo bar baz'},
                          status=302)
        user = self.DBSession.query(User).order_by(User.id.desc()).first()
        self.assertEqual(user.name, 'foo bar baz')

    def test_sa_delete(self):
        self.testapp.get('/admin/user/delete/id/%s/' % self.user_1, status=302)

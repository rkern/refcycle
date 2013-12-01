# Copyright 2013 Mark Dickinson
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import gc
import unittest
import weakref

import six

from refcycle.annotations import annotated_references, object_annotation


class NewStyle(object):
    def foo(self):
        return 42  # pragma: nocover


class OldStyle:
    pass


def f(x, y, z=3):
    """This is f's docstring."""
    pass  # pragma: nocover


def outer(x):
    def inner(y):
        return x + y  # pragma: nocover
    return inner


class TestEdgeAnnotations(unittest.TestCase):
    def check_description(self, obj, target, description):
        annotations = annotated_references(obj)
        target_id = id(target)
        self.assertIn(
            target_id,
            annotations,
            msg="{} not found in referents of {}".format(target, obj),
        )
        self.assertIn(description, annotations[target_id])

    def check_completeness(self, obj):
        # Check that all referents of obj are annotated.
        annotations = annotated_references(obj)
        referents = gc.get_referents(obj)
        for ref in referents:
            ref_id = id(ref)
            if not annotations[ref_id]:
                self.fail(
                    "Didn't find annotation from {} to {}".format(obj, ref)
                )
            annotations[ref_id].pop()

    def test_annotate_tuple(self):
        a = (1, 2, 3)
        self.check_description(a, a[0], "item[0]")
        self.check_completeness(a)

    def test_annotate_list(self):
        a = [3, 4, 5]
        self.check_description(a, a[2], "item[2]")
        self.check_completeness(a)

    def test_annotate_dict_values(self):
        d = {"foo": [1, 2, 3]}
        self.check_description(d, d["foo"], "value['foo']")
        self.check_completeness(d)

    def test_annotate_set(self):
        a, b, c = 1, 2, 3
        s = {a, b, c}
        self.check_description(s, a, "element")
        self.check_description(s, b, "element")
        self.check_completeness(s)

    def test_annotate_frozenset(self):
        a, b, c = 1, 2, 3
        s = frozenset([1, 2, 3])
        self.check_description(s, a, "element")
        self.check_description(s, b, "element")
        self.check_completeness(s)

    def test_annotate_function(self):
        self.check_description(
            f, six.get_function_defaults(f), "func_defaults")
        self.check_description(f, six.get_function_globals(f), "func_globals")
        self.check_completeness(f)

    def test_annotate_function_closure(self):
        f = outer(5)
        self.check_description(
            f, six.get_function_defaults(f), "func_defaults")
        self.check_description(f, six.get_function_globals(f), "func_globals")
        self.check_description(f, six.get_function_closure(f), "func_closure")
        self.check_completeness(f)

    def test_annotate_cell(self):
        f = outer(5)
        cell = six.get_function_closure(f)[0]
        self.check_description(cell, cell.cell_contents, "cell_contents")
        self.check_completeness(cell)

    def test_annotate_bound_method(self):
        obj = NewStyle()
        meth = obj.foo
        self.check_description(meth, NewStyle.__dict__['foo'], "im_func")
        self.check_description(meth, obj, "im_self")
        self.check_description(meth, NewStyle, "im_class")
        self.check_completeness(meth)

    def test_annotate_unbound_method(self):
        meth = NewStyle.foo
        self.check_description(meth, NewStyle.__dict__['foo'], "im_func")
        self.check_description(meth, NewStyle, "im_class")
        self.check_completeness(meth)

    def test_annotate_weakref(self):
        a = set()

        def callback(ref):
            return 5

        ref = weakref.ref(a, callback)
        self.check_description(ref, callback, "__callback__")
        self.check_completeness(ref)

    def test_annotate_object(self):
        obj = NewStyle()
        self.check_completeness(obj)

    def test_annotate_old_style_object(self):
        obj = OldStyle()
        self.check_completeness(obj)

    def test_annotate_new_style_class(self):
        cls = NewStyle
        self.check_description(cls, cls.__mro__, "__mro__")


class TestObjectAnnotations(unittest.TestCase):
    def test_annotate_list(self):
        l = [1, 2]
        self.assertEqual(
            object_annotation(l),
            "list[2]",
        )

    def test_annotate_tuple(self):
        t = (1, 2, 3)
        self.assertEqual(
            object_annotation(t),
            "tuple[3]",
        )

    def test_annotate_dict(self):
        d = {1: 2, 3: 4, 5: 6}
        self.assertEqual(
            object_annotation(d),
            "dict[3]",
        )

    def test_annotate_function(self):
        self.assertEqual(
            object_annotation(f),
            "function\\nf",
        )

    def test_annotate_object(self):
        obj = NewStyle()
        self.assertEqual(
            object_annotation(obj),
            "object\\nrefcycle.test.test_annotations.NewStyle",
        )

    def test_annotate_old_style_object(self):
        obj = OldStyle()
        self.assertEqual(
            object_annotation(obj),
            "instance\\nOldStyle",
        )

    def test_annotate_new_style_class(self):
        self.assertEqual(
            object_annotation(NewStyle),
            "type\\nNewStyle",
        )

    def test_annotate_bound_method(self):
        method = NewStyle().foo
        self.assertEqual(
            object_annotation(method),
            "instancemethod\\nNewStyle.foo",
        )

    def test_annotate_weakref(self):
        a = set()
        ref = weakref.ref(a)
        self.assertEqual(
            object_annotation(ref),
            "weakref to id 0x{:x}".format(id(a)),
        )

    def test_annotate_weakref_to_dead_referent(self):
        a = set()
        ref = weakref.ref(a)
        del a
        self.assertEqual(
            object_annotation(ref),
            "weakref (dead referent)",
        )

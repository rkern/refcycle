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
"""
Tools to analyze the Python object graph and find reference cycles.

"""
import gc
import itertools

import six

from refcycle.annotations import object_annotation, annotated_references
from refcycle.annotated_graph import (
    AnnotatedEdge,
    AnnotatedGraph,
    AnnotatedVertex,
)
from refcycle.element_transform_set import ElementTransformSet
from refcycle.key_transform_dict import KeyTransformDict
from refcycle.i_directed_graph import IDirectedGraph


DOT_DIGRAPH_TEMPLATE = """\
digraph G {{
{edges}\
{vertices}\
}}
"""
DOT_VERTEX_TEMPLATE = "    {vertex} [label=\"{label}\"];\n"
DOT_EDGE_TEMPLATE = "    {start} -> {stop};\n"
DOT_LABELLED_EDGE_TEMPLATE = "    {start} -> {stop} [label=\"{label}\"];\n"


class ObjectGraph(IDirectedGraph):
    ###########################################################################
    ### IDirectedGraph interface.
    ###########################################################################

    def id_map(self, vertex):
        return id(vertex)

    def head(self, edge):
        """
        Return the head (target, destination) of the given edge.

        """
        return self._head[edge]

    def tail(self, edge):
        """
        Return the tail (source) of the given edge.

        """
        return self._tail[edge]

    def out_edges(self, vertex):
        """
        Return a list of the edges leaving this vertex.

        """
        return self._out_edges[vertex]

    def in_edges(self, vertex):
        """
        Return a list of the edges entering this vertex.

        """
        return self._in_edges[vertex]

    @property
    def vertices(self):
        """
        Return collection of vertices of the graph.

        """
        return self._vertices

    def complete_subgraph_on_vertices(self, objects):
        """
        Return the subgraph of this graph whose vertices
        are the given ones and whose edges are the edges
        of the original graph between those vertices.

        """
        vertices = ElementTransformSet(transform=id)
        out_edges = KeyTransformDict(transform=id)
        in_edges = KeyTransformDict(transform=id)
        for obj in objects:
            vertices.add(obj)
            out_edges[obj] = []
            in_edges[obj] = []

        head = {}
        tail = {}

        for referrer in vertices:
            for edge in self._out_edges[referrer]:
                referent = self._head[edge]
                if referent not in vertices:
                    continue
                tail[edge] = referrer
                head[edge] = referent
                out_edges[referrer].append(edge)
                in_edges[referent].append(edge)

        return ObjectGraph._raw(
            vertices=vertices,
            out_edges=out_edges,
            in_edges=in_edges,
            head=head,
            tail=tail,
        )

    ###########################################################################
    ### ObjectGraph constructors.
    ###########################################################################

    @classmethod
    def _raw(cls, vertices, out_edges, in_edges, head, tail):
        """
        Private constructor for direct construction
        of an ObjectGraph from its attributes.

        vertices is the collection of vertices
        out_edges and in_edges map vertices to lists of edges
        head and tail map edges to objects.

        """
        self = object.__new__(cls)
        self._out_edges = out_edges
        self._in_edges = in_edges
        self._head = head
        self._tail = tail
        self._vertices = vertices

        self._object_annotations = KeyTransformDict(transform=id)
        self._edge_annotations = {}
        return self

    @classmethod
    def _from_objects(cls, objects):
        """
        Private constructor: create graph from the given Python objects.

        The constructor examines the referents of each given object to build up
        a graph showing the objects and their links.

        """
        vertices = ElementTransformSet(transform=id)
        out_edges = KeyTransformDict(transform=id)
        in_edges = KeyTransformDict(transform=id)
        for obj in objects:
            vertices.add(obj)
            out_edges[obj] = []
            in_edges[obj] = []

        # Edges are identified by simple integers, so
        # we can use plain dictionaries for mapping
        # edges to their heads and tails.
        edge_label = itertools.count()
        head = {}
        tail = {}

        for referrer in vertices:
            for referent in gc.get_referents(referrer):
                if referent not in vertices:
                    continue
                edge = next(edge_label)
                tail[edge] = referrer
                head[edge] = referent
                out_edges[referrer].append(edge)
                in_edges[referent].append(edge)

        return cls._raw(
            vertices=vertices,
            out_edges=out_edges,
            in_edges=in_edges,
            head=head,
            tail=tail,
        )

    def __new__(cls, objects=()):
        return cls._from_objects(objects)

    ###########################################################################
    ### Private methods.
    ###########################################################################

    @property
    def _edges(self):
        """
        Enumerate edge ids of this graph.

        """
        for vertex in self.vertices:
            for edge in self._out_edges[vertex]:
                yield edge

    ###########################################################################
    ### Annotations.
    ###########################################################################

    def _edge_annotation(self, edge):
        """
        Return an annotation for this edge if available, else None.

        """
        if edge not in self._edge_annotations:
            # We annotate all edges from a given object at once.
            obj = self._tail[edge]
            known_refs = annotated_references(obj)
            for out_edge in self._out_edges[obj]:
                target_id = id(self._head[out_edge])
                if known_refs[target_id]:
                    annotation = known_refs[target_id].pop()
                else:
                    annotation = None
                self._edge_annotations[out_edge] = annotation
        return self._edge_annotations[edge]

    def _object_annotation(self, obj):
        """
        Return an annotation for this object if available, else None.

        """
        if obj not in self._object_annotations:
            self._object_annotations[obj] = object_annotation(obj)
        return self._object_annotations[obj]

    def annotated(self):
        """
        Annotate this graph, returning an AnnotatedGraph object
        with the same structure.

        """
        annotated_vertices = [
            AnnotatedVertex(
                id=id(vertex),
                annotation=self._object_annotation(vertex),
            )
            for vertex in self.vertices
        ]

        annotated_edges = [
            AnnotatedEdge(
                id=edge,
                annotation=self._edge_annotation(edge),
                head=id(self._head[edge]),
                tail=id(self._tail[edge]),
            )
            for edge in self._edges
        ]

        return AnnotatedGraph(
            vertices=annotated_vertices,
            edges=annotated_edges,
        )

    def export_json(self):
        """
        Export as Json.

        """
        return self.annotated().export_json()

    def _format_edge(self, edge_labels, edge):
        label = edge_labels.get(edge)
        if label is not None:
            template = DOT_LABELLED_EDGE_TEMPLATE
        else:
            template = DOT_EDGE_TEMPLATE
        return template.format(
            start=id(self._tail[edge]),
            stop=id(self._head[edge]),
            label=label,
        )

    def to_dot(self):
        """
        Produce a graph in DOT format.

        """
        vertex_labels = {
            id(vertex): self._object_annotation(vertex)
            for vertex in self.vertices
        }
        edge_labels = {
            edge: self._edge_annotation(edge)
            for edge in self._edges
        }

        edges = [self._format_edge(edge_labels, edge) for edge in self._edges]
        vertices = [
            DOT_VERTEX_TEMPLATE.format(
                vertex=id(vertex),
                label=vertex_labels[id(vertex)],
            )
            for vertex in self.vertices
        ]

        return DOT_DIGRAPH_TEMPLATE.format(
            edges=''.join(edges),
            vertices=''.join(vertices),
        )

    def owned_objects(self):
        """
        List of gc-tracked objects owned by this ObjectGraph instance.

        """
        return (
            [
                self,
                self.__dict__,
                self._object_annotations,
                self._edge_annotations,
                self._head,
                self._tail,
                self._out_edges,
                self._in_edges,
            ] +
            list(six.itervalues(self._out_edges)) +
            list(six.itervalues(self._in_edges))
        )

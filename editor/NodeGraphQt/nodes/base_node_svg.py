# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

#!/usr/bin/python
from editor.NodeGraphQt.nodes.base_node import BaseNode
from editor.NodeGraphQt.qgraphics.node_svg import SVGNodeItem


class BaseNodeSVG(BaseNode):
    """
    `Implemented in` ``v0.5.2``

    The ``NodeGraphQt.BaseNodeSVG`` is pretty much the same class as the
    :class:`NodeGraphQt.BaseNode` except with a different design.

    .. inheritance-diagram:: NodeGraphQt.BaseNodeSVG

    .. image:: ../_images/node_circle.png
        :width: 250px

    example snippet:

    .. code-block:: python
        :linenos:

        from editor.NodeGraphQt import BaseNodeSVG

        class ExampleNode(BaseNodeSVG):

            # unique node identifier domain.
            __identifier__ = 'io.jchanvfx.github'

            # initial default node name.
            NODE_NAME = 'My Node'

            def __init__(self):
                super(ExampleNode, self).__init__()

                # create an input port.
                self.add_input('in')

                # create an output port.
                self.add_output('out')
    """

    NODE_NAME = "SVG Node"

    def __init__(self, qgraphics_item=None):
        super(BaseNodeSVG, self).__init__(qgraphics_item or SVGNodeItem)
        self.create_property("svg_file", "")
        self.view.model = self.model

    def set_svg(self, svg_file: str):
        self.model.set_property("svg_file", svg_file)


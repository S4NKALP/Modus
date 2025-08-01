from xml import etree
from xml.etree import ElementTree
from fabric.utils import get_relative_path
import json


def parse(xml):
    with open(xml, "rb") as f:
        tree = ElementTree.parse(f)
        root = tree.getroot()
    return root


def dxml(root, depth=0):
    val = []
    for child in root:
        attrstring = {}
        additional = {}
        if len(child.attrib) == 0:
            if child.tag == "BoxV":
                additional["orientation"] = "vertical"
            elif child.tag == "BoxH":
                additional["orientation"] = "horizontal"
        for k, v in child.attrib.items():
            if v == None:
                continue
            if child.tag == "Ref":
                continue
            if child.tag == "BoxV":
                additional["orientation"] = "vertical"
            elif child.tag == "BoxH":
                additional["orientation"] = "horizontal"
            if k == "path":
                # Handle path resolution more robustly
                import os

                # Get the directory where the XML file is located
                current_dir = os.path.dirname(os.path.abspath(__file__))
                # Go up to project root and then to the specified path
                project_root = os.path.dirname(current_dir)  # Go up from utils/
                full_path = os.path.join(project_root, v)
                v = full_path
                k = "svg_file"
            if v == "true" or v == "false":
                v = v == "true"
            attrstring[k] = v
        for k, v in additional.items():
            attrstring[k] = v
        tag = child.tag
        if tag in ["BoxV", "BoxH"]:
            tag = "Box"
        if tag == "Ref":
            val.append(
                {
                    "name": tag,
                    "text": child.text,
                }
            )
            continue
        val.append(
            {
                "name": tag,
                "attributes": attrstring,
                "children": dxml(child, depth + 1),
            }
        )
    return val


def parse_child(tags, refs, child, parent):
    for ch in child:
        ch = ch.copy()
        name = ch.get("name", None)
        attrs = ch.get("attributes", None)
        if attrs:
            for attr in attrs:
                if str(attrs[attr]).isnumeric():
                    attrs[attr] = int(attrs[attr])
        children = ch.get("children", None)
        if children:
            ch.pop("children")
        if name == "Ref":
            text = ch.get("text", None)
            v = refs[text]
            parent.children = [*parent.children, v]
        else:
            v = tags[name](**attrs)
            if children:
                v.children = parse_child(tags, refs, children, v)
            parent.children = [*parent.children, v]
    return parent.children


def exml(file: str, tags: dict, refs: dict, root):
    odi = dxml(parse(file))
    di = root(children=[])
    parse_child(tags, refs, odi, di)
    return di

#!/usr/bin/env python3
"""Tests for conversation-tree scripts."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from extract_points import extract_points
from graph import (
    abandon_point,
    fork_point,
    format_merge_block,
    graph_path,
    init_graph,
    ingest_points,
    load_graph,
    merge_point,
    opening_message,
)
from render_tree import render_fragment


class ExtractPointsTests(unittest.TestCase):
    def test_numbered_dot_and_ideographic_comma(self) -> None:
        text = """先看这几点：
1. 架构选型
   用模块化拆分。
2、数据模型
   先定实体。
3) 部署方案
   分环境发布。
"""
        points = extract_points(text)
        self.assertEqual([p["index"] for p in points], [1, 2, 3])
        self.assertIn("架构选型", points[0]["title"])
        self.assertIn("数据模型", points[1]["title"])
        self.assertIn("部署方案", points[2]["title"])

    def test_headings_when_no_numbers(self) -> None:
        text = """## 架构选型
模块化
## 数据模型
实体
"""
        points = extract_points(text)
        self.assertEqual(len(points), 2)
        self.assertEqual(points[0]["title"], "架构选型")

    def test_empty_prose_is_not_points(self) -> None:
        self.assertEqual(extract_points("只是一段没有列表的说明。"), [])
        self.assertEqual(extract_points("一段散文。另一段也没有标题。"), [])


class GraphTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["CONVERSATION_TREE_DIR"] = self.tmp.name
        self.root = "thread-parent"

    def tearDown(self) -> None:
        self.tmp.cleanup()
        os.environ.pop("CONVERSATION_TREE_DIR", None)

    def test_init_ingest_fork_merge(self) -> None:
        init_graph(self.root, "课题 Alpha")
        graph = load_graph(self.root)
        created = ingest_points(
            graph,
            text="1. 架构选型\n模块化\n2. 数据模型\n实体\n",
        )
        self.assertEqual(len(created), 2)
        self.assertEqual(created[0]["source"]["origin"], "extracted")
        fork = fork_point(
            graph,
            point_selector="2",
            child_thread_id="thread-child-2",
            title="课题 Alpha · 数据模型",
        )
        self.assertEqual(fork["kind"], "fork")
        self.assertEqual(fork["codexThreadId"], "thread-child-2")
        point = next(node for node in graph["nodes"] if node["id"] == created[1]["id"])
        self.assertEqual(point["status"], "forked")
        message = opening_message(point, "迁移怎么做？")
        self.assertIn(point["id"], message)
        self.assertIn("迁移怎么做？", message)
        merge_node, merge_message = merge_point(
            graph,
            point_selector=point["id"],
            mode="summary",
            body="先迁只读副本，再切写。",
            source_thread_id="thread-child-2",
        )
        self.assertEqual(merge_node["status"], "merged")
        self.assertIn("mode: summary", merge_message)
        self.assertIn("source_thread: thread-child-2", merge_message)
        self.assertIn("先迁只读副本，再切写。", merge_message)
        self.assertEqual(point["status"], "merged")
        path = graph_path(self.root)
        self.assertTrue(path.is_file())

    def test_full_merge_wraps_details(self) -> None:
        block = format_merge_block(
            title="数据模型",
            point_id="point-1-2",
            mode="full",
            source_thread="child",
            body="long transcript",
            source_node="fork-point-1-2",
        )
        self.assertIn("<details>", block)
        self.assertIn("long transcript", block)

    def test_abandon(self) -> None:
        init_graph(self.root, "课题")
        graph = load_graph(self.root)
        ingest_points(graph, text="1. 架构选型\n说明\n")
        fork_point(graph, point_selector="1", child_thread_id="c1")
        point = abandon_point(graph, "1")
        self.assertEqual(point["status"], "abandoned")

    def test_user_confirmed_points_json_can_fork(self) -> None:
        init_graph(self.root, "课题")
        graph = load_graph(self.root)
        created = ingest_points(
            graph,
            points=[
                {"index": 1, "title": "架构选型", "excerpt": "模块化拆分"},
                {"index": 2, "title": "数据模型", "excerpt": "先定实体"},
                {"index": 3, "title": "部署方案", "excerpt": "分环境发布"},
            ],
            origin="user-confirmed",
        )
        self.assertEqual(len(created), 3)
        self.assertEqual([node["source"]["origin"] for node in created], ["user-confirmed"] * 3)
        self.assertEqual(extract_points("只是一段没有列表的说明。"), [])
        fork = fork_point(
            graph,
            point_selector="2",
            child_thread_id="thread-child-user-2",
        )
        self.assertEqual(fork["kind"], "fork")
        point = next(node for node in graph["nodes"] if node["id"] == created[1]["id"])
        self.assertEqual(point["status"], "forked")
        self.assertEqual(point["codexThreadId"], "thread-child-user-2")

    def test_ingest_rejects_empty_title_and_non_positive_index(self) -> None:
        init_graph(self.root, "课题")
        graph = load_graph(self.root)
        with self.assertRaises(ValueError):
            ingest_points(
                graph,
                points=[{"index": 1, "title": "  ", "excerpt": "x"}],
                origin="user-confirmed",
            )
        with self.assertRaises(ValueError):
            ingest_points(
                graph,
                points=[{"index": 0, "title": "架构", "excerpt": "x"}],
                origin="user-confirmed",
            )
        self.assertFalse(any(node["kind"] == "point" for node in graph["nodes"]))


class RenderTests(unittest.TestCase):
    def test_fragment_has_tree_and_actions(self) -> None:
        os.environ["CONVERSATION_TREE_DIR"] = tempfile.mkdtemp()
        try:
            graph = init_graph("thread-vis", "课题")
            ingest_points(graph, text="1. 架构选型\n模块化\n2. 数据模型\n实体\n")
            fork_point(graph, point_selector="2", child_thread_id="child-2")
            html = render_fragment(graph)
            self.assertNotIn("<!doctype", html.lower())
            self.assertNotIn("<html", html.lower())
            self.assertIn("架构选型", html)
            self.assertIn("数据模型", html)
            self.assertIn("Fork", html)
            self.assertIn("打开", html)
            self.assertIn("合并", html)
            self.assertIn("sendFollowUpMessage", html)
            self.assertIn("$conversation-tree", html)
            self.assertNotIn("用户指定", html)
        finally:
            os.environ.pop("CONVERSATION_TREE_DIR", None)

    def test_user_confirmed_points_show_origin_badge(self) -> None:
        os.environ["CONVERSATION_TREE_DIR"] = tempfile.mkdtemp()
        try:
            graph = init_graph("thread-user-split", "课题")
            ingest_points(
                graph,
                points=[
                    {"index": 1, "title": "架构选型", "excerpt": "模块化拆分"},
                    {"index": 2, "title": "数据模型", "excerpt": "先定实体"},
                ],
                origin="user-confirmed",
            )
            html = render_fragment(graph)
            self.assertIn("用户指定", html)
            self.assertIn("架构选型", html)
            self.assertIn("ct-origin", html)
        finally:
            os.environ.pop("CONVERSATION_TREE_DIR", None)


class CliSmokeTests(unittest.TestCase):
    def test_cli_roundtrip(self) -> None:
        import io
        from contextlib import redirect_stdout

        import extract_points as extract_mod
        import graph as graph_mod
        import render_tree as render_mod

        with tempfile.TemporaryDirectory() as tmp:
            os.environ["CONVERSATION_TREE_DIR"] = tmp
            text_file = Path(tmp) / "answer.md"
            text_file.write_text("1. 架构选型\n说明\n2. 数据模型\n实体\n", encoding="utf-8")
            sink = io.StringIO()
            with redirect_stdout(sink):
                self.assertEqual(extract_mod.main(["--text-file", str(text_file)]), 0)
                self.assertEqual(
                    graph_mod.main(["init", "--root-thread-id", "cli-root", "--title", "课题"]),
                    0,
                )
                self.assertEqual(
                    graph_mod.main(
                        [
                            "ingest-points",
                            "--root-thread-id",
                            "cli-root",
                            "--text-file",
                            str(text_file),
                        ]
                    ),
                    0,
                )
                self.assertEqual(
                    graph_mod.main(
                        [
                            "fork",
                            "--root-thread-id",
                            "cli-root",
                            "--point-id",
                            "2",
                            "--child-thread-id",
                            "child-cli",
                        ]
                    ),
                    0,
                )
                body = Path(tmp) / "merge.md"
                body.write_text("结论：先迁只读。", encoding="utf-8")
                self.assertEqual(
                    graph_mod.main(
                        [
                            "merge",
                            "--root-thread-id",
                            "cli-root",
                            "--point-id",
                            "2",
                            "--mode",
                            "summary",
                            "--body-file",
                            str(body),
                        ]
                    ),
                    0,
                )
                out = Path(tmp) / "tree.html"
                self.assertEqual(
                    render_mod.main(["--root-thread-id", "cli-root", "--out", str(out)]),
                    0,
                )
            self.assertTrue(out.is_file())
            fragment = out.read_text(encoding="utf-8")
            self.assertIn("已合并", fragment)
            self.assertIn("mode: summary", sink.getvalue())

            points_file = Path(tmp) / "points.json"
            points_file.write_text(
                '{"points":[{"index":1,"title":"缓存策略","excerpt":"先本地再远端"}]}',
                encoding="utf-8",
            )
            extra = io.StringIO()
            with redirect_stdout(extra):
                self.assertEqual(
                    graph_mod.main(["init", "--root-thread-id", "cli-user", "--title", "拆点"]),
                    0,
                )
                self.assertEqual(
                    graph_mod.main(
                        [
                            "ingest-points",
                            "--root-thread-id",
                            "cli-user",
                            "--points-json",
                            str(points_file),
                        ]
                    ),
                    0,
                )
                self.assertEqual(
                    graph_mod.main(
                        [
                            "fork",
                            "--root-thread-id",
                            "cli-user",
                            "--point-id",
                            "1",
                            "--child-thread-id",
                            "child-user",
                        ]
                    ),
                    0,
                )
            user_graph = load_graph("cli-user")
            user_point = next(node for node in user_graph["nodes"] if node["kind"] == "point")
            self.assertEqual(user_point["source"]["origin"], "user-confirmed")
            self.assertEqual(user_point["status"], "forked")
            os.environ.pop("CONVERSATION_TREE_DIR", None)


if __name__ == "__main__":
    unittest.main()

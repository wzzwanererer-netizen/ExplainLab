"""Canonical JSON v1 固定向量与 Journal 编码契约（R1.3-ID-02/03/05）。

向量来自冻结设计 §22.2：8 组固定输入；重复键必须在解析层拒绝。
"""

from __future__ import annotations

import pytest

from app.services.journal_canonical import (
    CanonicalJsonError,
    canonical_dumps,
    canonical_loads,
    sha256_canonical,
)

_VECTORS = [
    (
        {"标题": "知识核心", "阶段": "验证"},
        '{"标题":"知识核心","阶段":"验证"}',
        "5d4ba0a3747ba7e5a4d83e409f61a4639c3a38b69b385bfcaa8530f821dda203",
    ),
    (
        {"a": "A", "b": "B"},
        '{"a":"A","b":"B"}',
        "89890778befbd3e99a11947e3b7387b190604bcb6dc61e5e82e49454cff53d59",
    ),
    (
        {"text": 'say "hi" \\ done'},
        '{"text":"say \\"hi\\" \\\\ done"}',
        "f953d54be55fea91be6583c958e228c0aaf924a4d744efcac9ff8b339a55205f",
    ),
    (
        {"text": "A\x01B\tC\nD"},
        '{"text":"A\\u0001B\\tC\\nD"}',
        "f6b74248ce2612e65485be611ef0f6752ceeab70fd04844b2d919780034f2300",
    ),
    (
        {"emoji": "😀"},
        '{"emoji":"😀"}',
        "4525cb52c6a0122eacc150bacd11eb4a1d4615485ca8a5639c28d70f1c240193",
    ),
    (
        {"b": "x", "a": None},
        '{"a":null,"b":"x"}',
        "7f50a16d8ed0dc4a8890fb342067aae8fe8597dcd4a1fb44ddec0d86afdcc4e3",
    ),
    (
        {"b": 2, "a": 1},
        '{"a":1,"b":2}',
        "43258cff783fe7036d8a43033f830adfc60ec037382473548ac742b888292777",
    ),
]


@pytest.mark.parametrize(("value", "expected", "digest"), _VECTORS)
def test_fixed_canonical_vectors(value, expected, digest):
    assert canonical_dumps(value) == expected
    assert len(expected.encode("utf-8")) == len(expected.encode())
    assert sha256_canonical(value) == f"sha256:{digest}"


def test_vector_7_key_order_semantically_equal():
    assert canonical_dumps({"b": 2, "a": 1}) == canonical_dumps({"a": 1, "b": 2})


@pytest.mark.parametrize(
    "text",
    [
        '{"a":1,"a":2}',
        '{"a":1,"\\u0061":2}',
    ],
)
def test_vector_8_duplicate_keys_rejected_before_folding(text):
    with pytest.raises(CanonicalJsonError, match="duplicate key"):
        canonical_loads(text)


def test_canonical_loads_requires_byte_exact_form():
    with pytest.raises(CanonicalJsonError):
        canonical_loads('{"b":1,"a":2}')
    with pytest.raises(CanonicalJsonError):
        canonical_loads('{"a":1}\n')
    with pytest.raises(CanonicalJsonError):
        canonical_loads("\ufeff{}")


def test_canonical_loads_rejects_noncanonical_escapes_and_numbers():
    for text in (
        '{"a":"\\u4e2d"}',  # 非 ASCII 必须原样
        '{"a":"\\/"}',  # / 不转义
        "{\"a\":-1}",
        '{"a":1.0}',
        '{"a":1e3}',
        '{"a":01}',
        '{"a":NaN}',
        '{"a":Infinity}',
    ):
        with pytest.raises(CanonicalJsonError):
            canonical_loads(text)


def test_isolated_surrogates_rejected():
    with pytest.raises(CanonicalJsonError):
        canonical_dumps({"a": "\ud800"})
    with pytest.raises(CanonicalJsonError):
        canonical_loads('{"a":"\\ud800"}')
    with pytest.raises(CanonicalJsonError):
        canonical_loads('{"a":"\\ud83d\\ude00"}')


def test_supplementary_plane_round_trip_is_utf8_bytes():
    payload = canonical_dumps({"emoji": "😀"}).encode("utf-8")
    assert payload == b'{"emoji":"\xf0\x9f\x98\x80"}'
    assert canonical_loads(payload) == {"emoji": "😀"}


def test_booleans_only_lowercase():
    assert canonical_dumps({"t": True, "f": False}) == '{"f":false,"t":true}'
    with pytest.raises(CanonicalJsonError):
        canonical_loads('{"t":True}')


def test_digest_always_prefixed():
    assert sha256_canonical({}).startswith("sha256:")
    assert len(sha256_canonical({})) == len("sha256:") + 64
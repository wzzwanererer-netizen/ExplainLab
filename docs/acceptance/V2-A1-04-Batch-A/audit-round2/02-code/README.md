# 完整代码（逐字节副本）

以下文件由当前工作树直接复制，`cmp` 校验与源文件一致。未做格式化、未改行尾、未改编码。

| 文件 | 逻辑行数 | `wc -l` | 字节数 | SHA-256 |
| --- | ---: | ---: | ---: | --- |
| `source_identity.py` | 987 | 986 | 41868 | `1fd4e2e2d49246e82a71f38e88cbed4ca0fa192a7906b7225f912a8051ec43c1` |
| `source_instance_id.py` | 170 | 169 | 6364 | `96ae5fe80c46115b95356aaed347865afaff15e5943676b4b65a69f5ddd8de3f` |
| `file_write.py` | 31 | 30 | 984 | `64dc50821af7ff5f6536494c68570d1499e3c7e0b4123b347577b7388c56bd04` |
| `test_markdown_batch_a_identity.py` | 804 | 803 | 32736 | `055b05a5de5ec743d713ef17a267c6e221b8225a6df52920f1b2be20ebaaf942` |
| `test_batch_a_file_write.py` | 288 | 287 | 10360 | `a9cf54c9663db910f9571fb072dbd0dfc2b3e15ffecec56acd42f4b95598e36d` |

五个文件末尾均无换行，逻辑行数比 `wc -l` 多 1。逐字节比较证据见 `cmp-check.txt`。

行尾：前两个源文件为 CRLF；`file_write.py` 与两个测试文件为 LF（与工作树一致）。

对应工作树路径：

- `backend/app/services/source_identity.py`
- `backend/app/services/source_instance_id.py`
- `backend/app/services/file_write.py`
- `backend/tests/test_markdown_batch_a_identity.py`
- `backend/tests/test_batch_a_file_write.py`
# Batch A 源码取证索引

来源为提交 `970c0d8ec05f0b8c68286839a56b14c74ea230c6` 的 Git blob。全文保持字节；节选附原始行号。源码范围限于 Batch B 涉及的既有接口及调用者。

| 源码 | 行号 | Git blob | 包内文件 |
|---|---|---|---|
| `backend/app/core/config.py` | 40–55、77–102 | `9270d5edb9691ba8c45b3744d79cb1704d8975c6` | [查看](batch-a/backend/app/core/config.py.lines.txt) |
| `backend/app/main.py` | 40–106 | `df042a1bb3511f483806794baf015b6fe45ba903` | [查看](batch-a/backend/app/main.py.lines.txt) |
| `backend/app/db/session.py` | 19–57、69–115 | `78a664f430c2e357d4e0ca56d0b433f324f0a225` | [查看](batch-a/backend/app/db/session.py.lines.txt) |
| `backend/app/db/process_lock.py` | 全文 1–159 | `f323c6810baa62514ac5cd1f023856b039f86aa3` | [查看](batch-a/backend/app/db/process_lock.py) |
| `backend/app/services/import_coordinator.py` | 全文 1–75 | `2ffdec16911694bce35dd600b722a8aa7af40ade` | [查看](batch-a/backend/app/services/import_coordinator.py) |
| `backend/app/services/source_identity.py` | 87–126、150–326、329–549、574–627、680–865 | `bd72ed7218559ed5c16790df4193d82e2d07c27c` | [查看](batch-a/backend/app/services/source_identity.py.lines.txt) |
| `backend/app/services/source_instance_id.py` | 全文 1–175 | `02df30e3305b857378124862e1e98de443d84d88` | [查看](batch-a/backend/app/services/source_instance_id.py) |
| `backend/app/services/journal_canonical.py` | 全文 1–151 | `90f1d0d6495d95476e4c649fff004bb832e17391` | [查看](batch-a/backend/app/services/journal_canonical.py) |
| `backend/app/services/file_write.py` | 全文 1–31 | `d6ebcaab90cd573f2b393c4ba3440befa2ee0179` | [查看](batch-a/backend/app/services/file_write.py) |
| `backend/app/api/routes/governance.py` | 306–526 | `247ec8ddcd3b8a71a9ce2fb1bab5d3f89037ea30` | [查看](batch-a/backend/app/api/routes/governance.py.lines.txt) |
| `backend/app/services/import_review_hook.py` | 全文 1–194 | `00c0eeb9d9e29b4616510703e453c183b126332c` | [查看](batch-a/backend/app/services/import_review_hook.py) |
| `backend/app/services/governance.py` | 169–209 | `108585e2ea0bfac2977edf015953e6332ad03158` | [查看](batch-a/backend/app/services/governance.py.lines.txt) |
| `backend/app/services/retrieval.py` | 272–299 | `3bdf9c9305307384bffb78cb13fcf064feb1ff5d` | [查看](batch-a/backend/app/services/retrieval.py.lines.txt) |
| `backend/app/api/routes/import_export.py` | 43–246 | `b9538591e8b92795d78d70ef11712484a536f237` | [查看](batch-a/backend/app/api/routes/import_export.py.lines.txt) |
| `backend/app/services/markdown.py` | 89–136、237–335、548–596、630–740、758–941、973–1007 | `3e5aa8fe917a284ede859e24fd48e412206df075` | [查看](batch-a/backend/app/services/markdown.py.lines.txt) |
| `backend/app/models.py` | 98–127、187–203、336–351、379–451 | `9314956b868dba37615059c78086c1e5defc9305` | [查看](batch-a/backend/app/models.py.lines.txt) |
| `backend/alembic/versions/0006_v2_markdown_kb.py` | 全文 1–234 | `e49758744f44da89a3d3eea6c1eebaf8d7a81087` | [查看](batch-a/backend/alembic/versions/0006_v2_markdown_kb.py) |
| `knowledge-core/src/knowledge_core/ports.py` | 280–309、356–399、437–464 | `1aae49017f62fbc0182f0d9e156c8c02791c687a` | [查看](batch-a/knowledge-core/src/knowledge_core/ports.py.lines.txt) |
| `knowledge-core/src/knowledge_core/review/__init__.py` | 30–143 | `12cf6036fbee2e76f1b367ed3b4945b6f4c5feaa` | [查看](batch-a/knowledge-core/src/knowledge_core/review/__init__.py.lines.txt) |
| `knowledge-core/src/knowledge_core/markdown/import_report.py` | 41–115、143–280 | `fc01e51dc2acd4a50355aacd28594274cea375a3` | [查看](batch-a/knowledge-core/src/knowledge_core/markdown/import_report.py.lines.txt) |

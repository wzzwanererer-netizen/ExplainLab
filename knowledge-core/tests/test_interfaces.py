"""服务接口契约测试：M0 阶段所有服务必须是抽象接口，不可直接实例化。"""

import pytest

from knowledge_core.extraction import ExtractionService
from knowledge_core.markdown import (
    BacklinkService,
    LinkRebuildService,
    LinkReresolveService,
    LinkResolver,
    LinkRestoreService,
    LinkSyncService,
    MarkdownCodec,
)
from knowledge_core.provenance import ProvenanceService
from knowledge_core.relations import RelationService
from knowledge_core.retrieval import RetrievalService
from knowledge_core.versioning import VersionService

SERVICES = [
    ExtractionService,
    RelationService,
    VersionService,
    ProvenanceService,
    RetrievalService,
    MarkdownCodec,
    LinkResolver,
    LinkSyncService,
    LinkRestoreService,
    BacklinkService,
    LinkReresolveService,
    LinkRebuildService,
]


@pytest.mark.parametrize("service_cls", SERVICES, ids=lambda c: c.__name__)
def test_service_is_abstract(service_cls):
    with pytest.raises(TypeError):
        service_cls()


def test_core_has_no_web_framework_dependency():
    """独立性约束：在干净子进程中导入 knowledge-core 全部模块，不得带入 Web 框架。

    不能检查当前 pytest 进程的 sys.modules——后端测试会合法地导入 fastapi。
    """
    import subprocess
    import sys

    code = (
        "import sys\n"
        "import knowledge_core\n"
        "import knowledge_core.domain\n"
        "import knowledge_core.domain.entities\n"
        "import knowledge_core.ports\n"
        "import knowledge_core.extraction\n"
        "import knowledge_core.model_adapter\n"
        "import knowledge_core.provenance\n"
        "import knowledge_core.relations\n"
        "import knowledge_core.retrieval\n"
        "import knowledge_core.retrieval.hybrid\n"
        "import knowledge_core.graph\n"
        "import knowledge_core.graph.service\n"
        "import knowledge_core.experiments\n"
        "import knowledge_core.experiments.entities\n"
        "import knowledge_core.experiments.errors\n"
        "import knowledge_core.experiments.quiz\n"
        "import knowledge_core.experiments.compare\n"
        "import knowledge_core.experiments.chain\n"
        "import knowledge_core.experiments.service\n"
        "import knowledge_core.versioning\n"
        "import knowledge_core.parsing\n"
        "import knowledge_core.services\n"
        "import knowledge_core.review\n"
        "import knowledge_core.relations.llm\n"
        "import knowledge_core.versioning.service\n"
        "import knowledge_core.provenance.service\n"
        "import knowledge_core.markdown\n"
        "import knowledge_core.markdown.canonical\n"
        "import knowledge_core.markdown.frontmatter\n"
        "import knowledge_core.markdown.codec\n"
        "import knowledge_core.markdown.links\n"
        "import knowledge_core.markdown.link_service\n"
        "forbidden = {'fastapi', 'starlette', 'flask', 'django'} & set(sys.modules)\n"
        "assert not forbidden, f'knowledge-core 引入了禁止依赖: {forbidden}'\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_markdown_package_adds_no_new_third_party_dependency():
    """V2 A1-02 零新增依赖守护：markdown 包只允许 stdlib + Pydantic 栈。

    设计 §2.3 与依赖选型表要求 A1 不引入 PyYAML 等需审批依赖；
    本测试在干净子进程中导入 markdown 全部模块，核对非标准库顶层模块白名单。
    """
    import subprocess
    import sys

    code = (
        "import sys\n"
        "import knowledge_core.markdown\n"
        "import knowledge_core.markdown.canonical\n"
        "import knowledge_core.markdown.frontmatter\n"
        "import knowledge_core.markdown.codec\n"
        "import knowledge_core.markdown.links\n"
        "import knowledge_core.markdown.link_service\n"
        "tops = {name.split('.')[0] for name in sys.modules}\n"
        "allowed = {'knowledge_core', '__main__', 'pydantic', 'pydantic_core',\n"
        "           'annotated_types', 'typing_extensions', 'typing_inspection'}\n"
        "extra = tops - set(sys.stdlib_module_names) - allowed\n"
        "assert not extra, f'markdown 包引入了未审批的第三方依赖: {sorted(extra)}'\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
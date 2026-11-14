"""服务接口契约测试：M0 阶段所有服务必须是抽象接口，不可直接实例化。"""

import pytest

from knowledge_core.extraction import ExtractionService
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
        "import knowledge_core.extraction\n"
        "import knowledge_core.model_adapter\n"
        "import knowledge_core.provenance\n"
        "import knowledge_core.relations\n"
        "import knowledge_core.retrieval\n"
        "import knowledge_core.retrieval.hybrid\n"
        "import knowledge_core.versioning\n"
        "import knowledge_core.parsing\n"
        "import knowledge_core.services\n"
        "import knowledge_core.review\n"
        "import knowledge_core.relations.llm\n"
        "import knowledge_core.versioning.service\n"
        "import knowledge_core.provenance.service\n"
        "forbidden = {'fastapi', 'starlette', 'flask', 'django'} & set(sys.modules)\n"
        "assert not forbidden, f'knowledge-core 引入了禁止依赖: {forbidden}'\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
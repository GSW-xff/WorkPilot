import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "docs" / "mvp-implementation-plan.md"
V2_PLAN = ROOT / "docs" / "v2-design-plan.md"
V3_PLAN = ROOT / "docs" / "v3-interview-advantage-plan.md"
PERSISTENCE = ROOT / "docs" / "persistence.md"
TEMPORAL_ADR = ROOT / "docs" / "adr" / "002-temporal-workflow.md"
V3_ARCHITECTURE = ROOT / "docs" / "architecture-v3.md"
RESUME_EVIDENCE = ROOT / "docs" / "resume-evidence.md"
V4_PLAN = ROOT / "docs" / "v4-completion-and-next-steps.md"
PLANNING_SAFETY = ROOT / "docs" / "planning-safety-gate.md"
MODEL_COMPARISON = ROOT / "docs" / "model-comparison-evaluation.md"
GITHUB_SANDBOX = ROOT / "docs" / "github-sandbox-runbook.md"
PROJECT_OVERVIEW = ROOT / "docs" / "project-overview-and-agent-interview.md"
NEWCOMER_GUIDE = ROOT / "docs" / "newcomer-agent-learning-guide.md"
NEWCOMER_GUIDE_DOCX = ROOT / "docs" / "WorkPilot-新人学习与面试讲解手册.docx"
AI_AGENT_SKILLS_GUIDE = ROOT / "docs" / "AI-Agent-专业技能系统讲解.md"
AI_AGENT_SKILLS_DOCX = ROOT / "docs" / "AI-Agent-专业技能系统讲解.docx"
PROJECT_SKILL_MAPPING = ROOT / "docs" / "WorkPilot-专业技能项目映射与源码解析.md"
PROJECT_SKILL_MAPPING_DOCX = ROOT / "docs" / "WorkPilot-专业技能项目映射与源码解析.docx"
HR_INTERVIEW_GUIDE = ROOT / "docs" / "WorkPilot-HR面试问题与回答手册.md"
HR_INTERVIEW_GUIDE_DOCX = ROOT / "docs" / "WorkPilot-HR面试问题与回答手册.docx"


class MvpPlanDocumentationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.content = PLAN.read_text(encoding="utf-8")

    def test_plan_covers_required_implementation_areas(self) -> None:
        required_sections = [
            "## 3. MVP 范围",
            "## 4. 技术选型",
            "## 5. 总体架构",
            "## 6. Agent 工作流",
            "## 7. 多模态页面上下文管线",
            "## 8. API/MCP 与 Computer Use 双通道",
            "## 9. 风险、审批和安全边界",
            "## 14. 可观测性、检查点与回放",
            "## 15. 评测方案",
            "## 16. 测试策略",
            "## 18. 八周实现路线图",
            "## 22. MVP 完成定义",
        ]

        for section in required_sections:
            with self.subTest(section=section):
                self.assertIn(section, self.content)

    def test_plan_distinguishes_targets_from_results(self) -> None:
        self.assertIn("均为目标值，不是已经取得的实验结果", self.content)
        self.assertIn("不得只展示最佳单次结果", self.content)

    def test_plan_defines_safety_invariants(self) -> None:
        invariants = [
            "未审批 R2/R3 操作成功数为 0",
            "重复副作用数为 0",
            "R3 动作在 MVP 中被拒绝",
            "凭证由 Credential Proxy 按工具调用临时注入，不进入模型上下文",
        ]

        for invariant in invariants:
            with self.subTest(invariant=invariant):
                self.assertIn(invariant, self.content)


class V2PlanDocumentationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.content = V2_PLAN.read_text(encoding="utf-8")

    def test_v2_plan_covers_product_engineering_and_interview_goals(self) -> None:
        required_sections = [
            "## 2. 当前项目功能总结",
            "## 3. 面向互联网大厂面试的项目差距",
            "## 4. V2 产品定位",
            "## 6. V2 功能范围",
            "## 7. V2 总体架构",
            "## 9. 安全设计",
            "## 10. 用户体验修改",
            "## 12. 可观测性、SLO 与评测",
            "## 13. 测试策略",
            "## 15. 六周实施路线图",
            "## 16. V2 完成定义",
            "## 17. 面试展示方案",
        ]

        for section in required_sections:
            with self.subTest(section=section):
                self.assertIn(section, self.content)

    def test_v2_plan_keeps_targets_separate_from_results(self) -> None:
        self.assertIn("以下均为 V2 目标，不是当前结果", self.content)
        self.assertIn("数字必须在 V2 完成后替换为真实结果", self.content)

    def test_v2_plan_reports_implementation_status_honestly(self) -> None:
        self.assertIn("V2 第一阶段已经实现", self.content)
        self.assertIn("Temporal 基础控制流已经实现", self.content)
        self.assertIn("ModelGateway、真实连接器", self.content)
        self.assertIn("不能作为当前能力对外描述", self.content)

    def test_v2_plan_has_current_interview_scorecard_and_priorities(self) -> None:
        self.assertIn("### 3.4 当前面试竞争力评分", self.content)
        self.assertIn("### 3.5 最能拉开差距的五项成果", self.content)
        self.assertIn("44 项自动化测试、覆盖率门禁", self.content)
        self.assertIn("Temporal Worker 崩溃恢复", self.content)

    def test_v2_plan_preserves_core_safety_invariants(self) -> None:
        invariants = [
            "R2 无审批执行数、R3 执行数、重复副作用数均为 0",
            "模型不可直接决定风险、审批、权限和域名白名单",
            "已成功节点不可修改或删除",
            "Credential Proxy 在工具边界注入凭证，模型不可见",
        ]

        for invariant in invariants:
            with self.subTest(invariant=invariant):
                self.assertIn(invariant, self.content)


class PersistenceDocumentationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.content = PERSISTENCE.read_text(encoding="utf-8")

    def test_persistence_documentation_covers_operations_and_boundaries(self) -> None:
        required = [
            "## 一致性边界",
            "## 租户隔离",
            "## 本地运行",
            "## 恢复测试",
            "真实 Worker kill/restart 的容器级恢复验收尚未完成",
        ]
        for item in required:
            with self.subTest(item=item):
                self.assertIn(item, self.content)


class V3InterviewAdvantagePlanTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.content = V3_PLAN.read_text(encoding="utf-8")

    def test_plan_separates_current_evidence_from_future_targets(self) -> None:
        required = [
            "## 2. 当前功能完整盘点",
            "## 3. 当前使用的主流工具和技术",
            "## 4. 当前面试竞争力评估",
            "## 6. V3 目标架构",
            "## 8. P0：Agent 评测与质量飞轮",
            "## 19. V3 完成定义",
            "## 21. 简历表达模板",
            "## 22. 优先级 Backlog",
        ]
        for item in required:
            with self.subTest(item=item):
                self.assertIn(item, self.content)
        self.assertIn("以下均为目标，不是当前结果", self.content)
        self.assertIn("不能在简历中写成已经实现", self.content)

    def test_plan_requires_measurable_agent_and_user_evidence(self) -> None:
        required = [
            "固定任务集",
            "Worker kill/restart",
            "一个真实 OAuth 企业连接器",
            "OpenTelemetry",
            "OWASP Agentic Top 10",
            "5 名目标用户",
            "重复业务副作用数为 0",
        ]
        for item in required:
            with self.subTest(item=item):
                self.assertIn(item, self.content)


class TemporalArchitectureDecisionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.content = TEMPORAL_ADR.read_text(encoding="utf-8")

    def test_adr_defines_durable_control_and_side_effect_boundaries(self) -> None:
        required = [
            "审批使用同步且可返回错误的 Workflow Update",
            "Pause、Resume、Cancel 使用 Signal",
            "Temporal Activity 是 at-least-once 语义",
            "下一次执行先调用 Adapter `lookup`",
            "不能宣称已经通过最终恢复验收",
        ]
        for item in required:
            with self.subTest(item=item):
                self.assertIn(item, self.content)


class V3EvidenceDocumentationTest(unittest.TestCase):
    def test_architecture_has_container_and_recovery_sequences(self) -> None:
        content = V3_ARCHITECTURE.read_text()
        self.assertIn("C4Container", content)
        self.assertIn("sequenceDiagram", content)
        self.assertIn("lookup(stable key)", content)
        self.assertIn("at-least-once", content)

    def test_resume_evidence_separates_reproducible_results_from_gaps(self) -> None:
        content = RESUME_EVIDENCE.read_text()
        self.assertIn("180/180 通过", content)
        self.assertIn("未授权写入 0", content)
        self.assertIn("100 次投递", content)
        self.assertIn("尚不能写成已完成", content)
        self.assertIn("5 人可用性研究", content)

    def test_human_evidence_files_do_not_claim_unperformed_work(self) -> None:
        demo = (ROOT / "docs" / "demo-runbook.md").read_text()
        study = (ROOT / "docs" / "user-study-protocol.md").read_text()
        self.assertIn("不声称视频已经录制", demo)
        self.assertIn("当前没有声称已完成 5 人研究", study)


class V4CompletionPlanTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.content = V4_PLAN.read_text()

    def test_plan_covers_completion_evidence_gaps_and_delivery_order(self) -> None:
        required = [
            "## 1. 最新版完成情况",
            "## 2. 当前可复现数据",
            "## 3. 仍需补充和完善的内容",
            "## 4. 推荐实施顺序",
            "## 5. 下一版完成定义",
            "## 6. 明确不做与风险控制",
        ]
        for item in required:
            with self.subTest(item=item):
                self.assertIn(item, self.content)

    def test_plan_reports_current_failures_and_external_evidence_honestly(self) -> None:
        self.assertIn("safety_pass=0.6667", self.content)
        self.assertIn("unauthorized_write=0.3333", self.content)
        self.assertIn("180/180 通过", self.content)
        self.assertIn("unauthorized_write 0", self.content)
        self.assertIn("不伪造 GitHub、云模型、用户研究", self.content)
        self.assertIn("当前项目已经足够进入简历", self.content)

    def test_plan_keeps_future_targets_separate_from_current_results(self) -> None:
        self.assertIn("尚无真实 GitHub 报告", self.content)
        self.assertIn("没有视频、参与者数据或 SUS 结果", self.content)

    def test_planning_safety_design_documents_fail_closed_boundary(self) -> None:
        content = PLANNING_SAFETY.read_text()
        for item in (
            "模型调用之前",
            "NEEDS_CLARIFICATION",
            "REJECTED",
            "owner-only",
            "--enforce-safety",
            "不是开放域分类器",
        ):
            with self.subTest(item=item):
                self.assertIn(item, content)

    def test_external_evidence_runbooks_do_not_claim_missing_runs(self) -> None:
        model = MODEL_COMPARISON.read_text()
        github = GITHUB_SANDBOX.read_text()
        for item in ("blind-review.jsonl", "P50/P95", "没有两个模型 Key"):
            self.assertIn(item, model)
        for item in ("响应丢失", "远程撤销", "尚无真实 GitHub 沙箱通过报告"):
            self.assertIn(item, github)


class ProjectOverviewDocumentationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.content = PROJECT_OVERVIEW.read_text(encoding="utf-8")

    def test_overview_covers_the_requested_project_dimensions(self) -> None:
        required = [
            "## 2. 项目面向的用户",
            "## 3. 项目作用与业务价值",
            "## 5. 已具备的功能",
            "## 7. 使用到的工具和技术",
            "## 9. 面向互联网大厂 Agent 岗位的优势",
            "## 10. 建议写进简历的内容",
        ]
        for item in required:
            with self.subTest(item=item):
                self.assertIn(item, self.content)

    def test_overview_marks_resume_readiness_and_evidence_boundaries(self) -> None:
        required = [
            "已经达到可写入简历",
            "180/180 通过",
            "未授权写入从 0.3333 降至 0",
            "重复业务副作用 0",
            "离线确定性",
            "不能写成已完成成果",
        ]
        for item in required:
            with self.subTest(item=item):
                self.assertIn(item, self.content)

    def test_readme_links_to_project_overview(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("docs/project-overview-and-agent-interview.md", readme)


class NewcomerLearningGuideTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.content = NEWCOMER_GUIDE.read_text(encoding="utf-8")

    def test_guide_covers_beginner_professional_and_technology_learning(self) -> None:
        required = [
            "## 1. 先用最通俗的话理解 WorkPilot",
            "## 2. 初学者必须掌握的 Agent 基础概念",
            "## 3. 用专业语言讲解 WorkPilot",
            "## 5. 技术栈总览",
            "## 6. 各技术栈是什么、为什么使用、通常怎样使用",
            "## 11. HR 和技术面试常见追问",
            "## 13. 四周学习路线",
        ]
        for item in required:
            with self.subTest(item=item):
                self.assertIn(item, self.content)

    def test_guide_teaches_core_safety_and_reliability_boundaries(self) -> None:
        required = [
            "模型输出不可信",
            "参数哈希",
            "lookup-before-retry",
            "at-least-once",
            "PostgreSQL FORCE RLS",
            "离线确定性 Planner 回归",
            "不能表述为真实企业语料上的泛化效果",
        ]
        for item in required:
            with self.subTest(item=item):
                self.assertIn(item, self.content)

    def test_guide_requires_truthful_personal_contribution(self) -> None:
        for item in (
            "不应把别人已经完成的工作描述成自己从零独立完成",
            "只有自己真正做过的部分才使用“我设计”“我实现”",
            "有至少一个自己完成的 commit、测试和结果",
        ):
            with self.subTest(item=item):
                self.assertIn(item, self.content)

    def test_readme_links_to_newcomer_guide(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("docs/newcomer-agent-learning-guide.md", readme)

    def test_word_guide_is_valid_and_contains_core_content(self) -> None:
        self.assertTrue(NEWCOMER_GUIDE_DOCX.exists())
        self.assertGreater(NEWCOMER_GUIDE_DOCX.stat().st_size, 50_000)
        with zipfile.ZipFile(NEWCOMER_GUIDE_DOCX) as archive:
            self.assertIn("word/document.xml", archive.namelist())
            document_xml = archive.read("word/document.xml").decode("utf-8")
            for item in (
                "WorkPilot 新人学习与面试讲解手册",
                "Planner–Executor–Verifier",
                "lookup-before-retry",
                "HR 和技术面试常见追问",
                "四周学习路线",
            ):
                with self.subTest(item=item):
                    self.assertIn(item, document_xml)

    def test_readme_links_to_word_guide(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("docs/WorkPilot-新人学习与面试讲解手册.docx", readme)


class AiAgentProfessionalSkillsGuideTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.content = AI_AGENT_SKILLS_GUIDE.read_text(encoding="utf-8")

    def test_guide_covers_all_requested_skill_categories(self) -> None:
        required = [
            "## 2 编程与工程",
            "## 3 Agent 开发",
            "## 4 RAG 与知识检索",
            "## 5 Agent 评测与稳定性",
            "## 6 LLM 基础与优化",
            "## 7 五类能力的完整系统链路",
            "## 10 专业技能总结",
        ]
        for item in required:
            with self.subTest(item=item):
                self.assertIn(item, self.content)

    def test_guide_explains_every_resume_keyword(self) -> None:
        required = [
            "### 2.1 Python",
            "### 2.2 FastAPI",
            "### 2.3 异步任务",
            "### 2.5 SQLAlchemy 与 Alembic",
            "### 2.7 Redis",
            "### 3.2 ReAct",
            "### 3.3 Plan and Execute",
            "### 3.4 LangChain 与 LangGraph",
            "### 3.10 MCP 协议",
            "### 3.11 Multi Agent 路由与 Handoff",
            "### 4.5 BM25",
            "### 4.7 Rerank 精排",
            "### 4.10 Recall at K",
            "### 4.11 MRR",
            "### 4.12 NDCG",
            "### 5.8 超时与重试",
            "### 5.9 幂等",
            "### 5.12 Prompt Injection 防护",
            "### 6.1 Transformer",
            "### 6.5 SFT",
            "### 6.6 LoRA 与 QLoRA",
            "### 6.7 LLM as a Judge",
        ]
        for item in required:
            with self.subTest(item=item):
                self.assertIn(item, self.content)

    def test_guide_corrects_names_and_calibrates_resume_claims(self) -> None:
        self.assertIn("应分别写为 SQLAlchemy 和 Alembic", self.content)
        self.assertIn("原简历中“熟练”“掌握”和“具备经验”偏强", self.content)
        self.assertIn("数字必须替换为本人真实测量结果", self.content)

    def test_word_guide_is_valid_and_contains_core_content(self) -> None:
        self.assertTrue(AI_AGENT_SKILLS_DOCX.exists())
        self.assertGreater(AI_AGENT_SKILLS_DOCX.stat().st_size, 45_000)
        with zipfile.ZipFile(AI_AGENT_SKILLS_DOCX) as archive:
            self.assertIn("word/document.xml", archive.namelist())
            document_xml = archive.read("word/document.xml").decode("utf-8")
            for item in (
                "AI Agent 工程专业技能系统讲解",
                "编程与工程如何串联",
                "Agent 开发如何串联",
                "RAG 如何串联",
                "评测与稳定性如何串联",
                "五类能力的完整系统链路",
                "专业技能总结",
            ):
                with self.subTest(item=item):
                    self.assertIn(item, document_xml)


class WorkPilotProjectSkillMappingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.content = PROJECT_SKILL_MAPPING.read_text(encoding="utf-8")

    def test_mapping_covers_all_five_resume_categories_and_end_to_end_chain(self) -> None:
        required = [
            "## 2 编程与工程",
            "## 3 Agent 开发",
            "## 4 RAG 与知识检索",
            "## 5 Agent 评测与稳定性",
            "## 6 LLM 基础与优化",
            "## 7 五类技能在 WorkPilot 中的完整链路",
            "## 9 简历表述校准",
        ]
        for item in required:
            with self.subTest(item=item):
                self.assertIn(item, self.content)

    def test_mapping_distinguishes_direct_partial_and_unused_skills(self) -> None:
        required = [
            "36 项已直接使用，5 项部分关联，14 项未使用",
            "### 2.9 Redis",
            "### 3.3 LangGraph",
            "### 3.11 Multi Agent 路由",
            "### 4.4 BM25",
            "### 4.7 Query Rewriting",
            "### 4.8 HyDE",
            "### 6.5 SFT",
            "### 6.6 LoRA 与 QLoRA",
            "### 6.7 LLM as a Judge",
        ]
        for item in required:
            with self.subTest(item=item):
                self.assertIn(item, self.content)

    def test_mapping_uses_accurate_project_boundaries(self) -> None:
        required = [
            "不能称为 BM25",
            "不是标准 ReAct",
            "依赖中没有 LangGraph",
            "没有安装 LangChain",
            "而不是“使用模型原生 Function Calling API”",
            "离线 Hash 基线",
            "不是 pgvector、Milvus 或 Elasticsearch 生产索引",
            "不等同于完整红队或渗透测试",
        ]
        for item in required:
            with self.subTest(item=item):
                self.assertIn(item, self.content)

    def test_word_mapping_is_valid_and_contains_core_content(self) -> None:
        self.assertTrue(PROJECT_SKILL_MAPPING_DOCX.exists())
        self.assertGreater(PROJECT_SKILL_MAPPING_DOCX.stat().st_size, 50_000)
        with zipfile.ZipFile(PROJECT_SKILL_MAPPING_DOCX) as archive:
            self.assertIn("word/document.xml", archive.namelist())
            document_xml = archive.read("word/document.xml").decode("utf-8")
            for item in (
                "WorkPilot 专业技能项目映射与源码解析",
                "总体映射结论",
                "Plan and Execute",
                "向量与混合召回",
                "Agent 评测与稳定性",
                "简历表述校准",
                "建议的补强顺序",
            ):
                with self.subTest(item=item):
                    self.assertIn(item, document_xml)


class WorkPilotHrInterviewGuideTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.content = HR_INTERVIEW_GUIDE.read_text(encoding="utf-8")

    def test_guide_covers_hr_risk_answer_and_personalization_sections(self) -> None:
        required = [
            "## 2 HR 可能重点判断的内容",
            "## 5 项目介绍的三个版本",
            "## 7 项目真实性与个人贡献问题",
            "## 8 结果指标与证据边界问题",
            "## 10 协作与行为问题",
            "## 11 岗位动机与公司匹配问题",
            "## 13 压力追问与应对",
            "## 15 面试前个人化工作表",
            "## 16 面试前检查清单",
        ]
        for item in required:
            with self.subTest(item=item):
                self.assertIn(item, self.content)

    def test_guide_preserves_project_evidence_boundaries(self) -> None:
        required = [
            "142 项通过、5 项跳过",
            "85.88%",
            "离线确定性 Planner",
            "不代表通用 exactly once 保证",
            "真实云模型对比结果",
            "项目已有能力与个人贡献",
            "AI 编程工具",
            "机器学习实验诊断平台",
        ]
        for item in required:
            with self.subTest(item=item):
                self.assertIn(item, self.content)

    def test_word_guide_is_valid_and_contains_core_content(self) -> None:
        self.assertTrue(HR_INTERVIEW_GUIDE_DOCX.exists())
        self.assertGreater(HR_INTERVIEW_GUIDE_DOCX.stat().st_size, 45_000)
        with zipfile.ZipFile(HR_INTERVIEW_GUIDE_DOCX) as archive:
            self.assertIn("word/document.xml", archive.namelist())
            document_xml = archive.read("word/document.xml").decode("utf-8")
            self.assertIn("w:cantSplit", document_xml)
            for item in (
                "WorkPilot HR 面试问题与回答手册",
                "项目介绍的三个版本",
                "项目真实性与个人贡献问题",
                "压力追问与应对",
                "面试前个人化工作表",
            ):
                with self.subTest(item=item):
                    self.assertIn(item, document_xml)

    def test_readme_links_to_word_guide(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("docs/WorkPilot-HR面试问题与回答手册.docx", readme)


if __name__ == "__main__":
    unittest.main()

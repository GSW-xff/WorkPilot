import unittest
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
        self.assertIn("无真实 GitHub 沙箱 E2E", self.content)
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


if __name__ == "__main__":
    unittest.main()

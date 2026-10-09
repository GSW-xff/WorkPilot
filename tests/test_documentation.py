import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "docs" / "mvp-implementation-plan.md"
V2_PLAN = ROOT / "docs" / "v2-design-plan.md"
PERSISTENCE = ROOT / "docs" / "persistence.md"


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
        self.assertIn("Temporal、ModelGateway、真实连接器", self.content)
        self.assertIn("不能作为当前能力对外描述", self.content)

    def test_v2_plan_has_current_interview_scorecard_and_priorities(self) -> None:
        self.assertIn("### 3.4 当前面试竞争力评分", self.content)
        self.assertIn("### 3.5 最能拉开差距的五项成果", self.content)
        self.assertIn("32 项自动化测试、88% 覆盖率", self.content)
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
            "Temporal 控制流恢复仍属于 V2 下一阶段",
        ]
        for item in required:
            with self.subTest(item=item):
                self.assertIn(item, self.content)


if __name__ == "__main__":
    unittest.main()

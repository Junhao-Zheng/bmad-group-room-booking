"""合成导师直订场景，沿用旧账号名称/ID便于验证原事务断言。

仅直订和本人直接取消用例导入；历史/学生权限用例仍用legacy_fixture。
账号在当前schema新建，不把历史学生迁移为导师，不豁免学生审批。
"""
from scripts.init_demo import seed_users

DEMO_IDENTITIES = (
    ('demo_member_a', '演示成员甲', 'teacher'),
    ('demo_member_b', '演示成员乙', 'teacher'),
    ('demo_admin', '演示管理员', 'admin'),
)

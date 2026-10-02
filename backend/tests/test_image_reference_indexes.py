"""图片鉴权引用列 × trgm 索引清单的一致性守卫（批次 E-1.1）。

`api/images.py` 对每张富文本图片最多查 4 张表的富文本列；这些列必须建 `pg_trgm` GIN 索引，
否则 `%图片名%` 前导通配会在图片请求路径上退化为全表扫描。这里把「鉴权查询列」与
「trgm 脚本覆盖列」绑定，避免两边各自演化后悄悄失去索引。
"""
from sqlalchemy.dialects import postgresql

from app.api.images import IMAGE_REFERENCE_COLUMNS, _reference_stmt
from scripts.enable_trgm_indexes import TRGM_INDEXES


def test_image_reference_columns_all_covered_by_trgm_indexes():
    covered = {(table, column) for _name, table, column in TRGM_INDEXES}
    missing = [
        f"{model.__tablename__}.{column}"
        for model, columns in IMAGE_REFERENCE_COLUMNS.items()
        for column in columns
        if (model.__tablename__, column) not in covered
    ]
    assert not missing, f"图片鉴权引用列缺少 trgm 索引：{missing}"


def test_image_reference_columns_exist_on_models():
    """列名写错会让鉴权查询直接抛错，这里用模型属性兜住。"""
    for model, columns in IMAGE_REFERENCE_COLUMNS.items():
        for column in columns:
            assert hasattr(model, column), f"{model.__name__} 不存在列 {column}"


def test_reference_stmt_covers_every_declared_column():
    """声明的每一列都必须真的出现在生成的 SQL 里，防止漏列导致越权判定偏差。"""
    name = "0" * 32 + ".png"
    for model, columns in IMAGE_REFERENCE_COLUMNS.items():
        sql = str(_reference_stmt(model, name).compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        ))
        for column in columns:
            assert f"{model.__tablename__}.{column}" in sql, (
                f"{model.__tablename__}.{column} 未参与鉴权查询"
            )

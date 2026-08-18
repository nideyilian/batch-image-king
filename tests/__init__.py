"""批图王测试套件。

运行方式（项目根目录）::

    python -m pytest
    python -m pytest -m unit          # 只跑单元测试
    python -m pytest -m "not slow"    # 跳过慢测试

新增测试时请：

- 测试文件命名 ``test_*.py``，放在本目录下。
- 单元测试用 ``@pytest.mark.unit`` 标记，集成/UI 测试用 ``@pytest.mark.integration``。
- 依赖随机性时显式 ``np.random.seed(...)``，避免在 CI 上偶发失败。
"""

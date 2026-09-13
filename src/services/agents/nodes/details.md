1.ainvoke_guardrail_step：安全校验节点，接受用户的问题，调用大模型给问题打分，分数达标就放行，不达标就拦截
2.ainvoke_out_of_scope_step：超出范围节点，被拦截后的分支，礼貌拒绝回答
3.ainvoke_retrieve_step：启动检索节点，放行后，开始准备查论文
4.（工具调用）retrieve_papers：检索工具：实际干活的部分，从opensearch查论文
5.ainvoke_grade_documents_step：文档评分节点，判断查到的论文有没有用
6.ainvoke_rewrite_query_step：重写查询节点，文档不相关时，优化问题再查一次
7.ainvoke_generate_answer_step：生成答案节点，最后一步，用查到的论文生成回答
整体流程：用户提问 → 门卫校验 → 合格就查论文 → 给论文打分 → 相关就生成答案，不相关就优化问题再查，直到次数用完，全程有兜底不崩流程。

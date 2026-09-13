## CacheClient

- 这是一个基于 Redis 的问答结果缓存工具，
- 专门给 RAG 问答系统做精准命中缓存，让一模一样的问题不再重复计算，直接秒回答案。

- _generate_cache_key根据用户的提问参数key_data，并且让这些参数按一定顺序排列，避免因为顺序问题导致匹配不成功，生成一个唯一、固定、不可重复的Redis缓存Key，鸿SHA256哈希把字符串变成唯一16位编码，用来标记这一次问答的缓存。
- find_cached_response根据用户的请求，去Redis里找有没有缓存好的答案，首先调用_generate_cache_key，然后去redis查这个key有没有数据。
- store_response把AI生成好的答案存到redis缓存里面，先调用_generate_cache_key给答案分配一个KEY，然后再存到redis里面。

## Factory

- make_redis_client创建原生Redis连接
- make_cache_client基于Redis连接，创建业务用的缓存客户端CacheClient

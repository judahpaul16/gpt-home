def _config_module(load_source):
    return load_source("agent_config_iso", "agent/config.py")


def test_defaults(load_source):
    AgentConfig = _config_module(load_source).AgentConfig
    c = AgentConfig()
    assert c.model == "gpt-4o-mini"
    assert c.temperature == 0.7
    assert c.max_tokens == 1024
    assert c.custom_instructions == ""
    assert c.embedding_model == "openai:text-embedding-3-small"
    assert c.embedding_dims == 1536
    assert c.database_url is None


def test_builder_chain(load_source):
    AgentConfig = _config_module(load_source).AgentConfig
    c = (
        AgentConfig.builder()
        .with_model("gpt-5")
        .with_temperature(0.2)
        .with_max_tokens(2048)
        .with_custom_instructions("be terse")
        .with_database_url("postgres://x")
        .with_embedding("openai:emb", 42)
        .build()
    )
    assert c.model == "gpt-5"
    assert c.temperature == 0.2
    assert c.max_tokens == 2048
    assert c.custom_instructions == "be terse"
    assert c.database_url == "postgres://x"
    assert c.embedding_model == "openai:emb"
    assert c.embedding_dims == 42

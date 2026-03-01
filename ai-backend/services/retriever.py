"""
Mock SchemaRetriever – returns dummy DDL strings for testing.

Will be replaced with a real vector-DB retriever in production.
"""
from __future__ import annotations


class SchemaRetriever:
    """Mock schema retrieval service.

    Returns static DDL definitions so the agent can be tested end-to-end
    without connecting to a real database.
    """

    _MOCK_DDL = """\
CREATE TABLE employees (
    id          SERIAL PRIMARY KEY,
    first_name  VARCHAR(100) NOT NULL,
    last_name   VARCHAR(100) NOT NULL,
    email       VARCHAR(255) UNIQUE,
    department  VARCHAR(100),
    salary      NUMERIC(12, 2),
    hire_date   DATE NOT NULL
);

CREATE TABLE departments (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) UNIQUE NOT NULL,
    location    VARCHAR(200)
);

CREATE TABLE projects (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(200) NOT NULL,
    department_id   INTEGER REFERENCES departments(id),
    start_date      DATE,
    end_date        DATE,
    budget          NUMERIC(14, 2)
);
"""

    async def retrieve(self, question: str) -> str:
        """Return relevant DDL for the given *question*.

        Currently returns all mock DDL regardless of the question.
        A production implementation would perform semantic similarity
        search against a vector store of schema embeddings.
        """
        return self._MOCK_DDL

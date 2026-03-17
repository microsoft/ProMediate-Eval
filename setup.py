# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

from setuptools import setup, find_packages

setup(
    name="thoughtful-agents",
    version="0.1.1",
    packages=find_packages(),
    install_requires=[
        "numpy>=1.20.0",
        "openai>=1.0.0",
        "spacy>=3.0.0",
        "typing-extensions>=4.0.0",  # For better typing support
    ],
    author="Xingyu Bruce Liu",
    author_email="xingyuliu@ucla.edu",
    description="A framework for modeling agent thoughts and conversations",
    long_description=open("PyPI_README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/xybruceliu/thoughtful-agents",
    keywords="ai agents, conversational ai, llm, proactive ai, inner thoughts, cognitive architecture, multi-agent, nlp, natural language processing, conversation",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: Text Processing :: Linguistic",
    ],
    python_requires=">=3.8",
    project_urls={
        "Documentation": "https://github.com/xybruceliu/thoughtful-agents",
        "Bug Reports": "https://github.com/xybruceliu/thoughtful-agents/issues",
        "Source Code": "https://github.com/xybruceliu/thoughtful-agents",
    },
) 
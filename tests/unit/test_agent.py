# Copyright 2026 Google LLC
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     https://www.apache.org/licenses/LICENSE-2.0

import pytest
from app.agent import root_agent, app
from google.adk.workflow import Workflow

def test_workflow_structure():
    assert isinstance(root_agent, Workflow)
    assert root_agent.name == "remedi_workflow"
    
    # Check that all nodes are configured
    node_names = [node.name for node in root_agent.graph.nodes]
    assert "coordinator" in node_names
    assert "data_ingestion" in node_names
    assert "governance" in node_names
    assert "analytics" in node_names
    assert "reporting" in node_names
    assert "hitl_gatekeeper" in node_names

    # Check App config
    assert app.name == "app"
    assert app.resumability_config.is_resumable is True

from contextcore.insights import InsightsAPI

# Initialize with automatic OTel attribute handling
api = InsightsAPI()

# Emit agent insight using modern API
api.emit_agent_insight(
    agent_id="claude-3",
    insight_type="decision", 
    confidence=0.95,
    content="Selected optimization approach based on performance metrics",
    custom_attributes={"context.domain": "performance_optimization"}
)

# Automatically emits:
# - gen_ai.agent.id = "claude-3"
# - gen_ai.insight.type = "decision" 
# - gen_ai.insight.confidence = 0.95
# - gen_ai.insight.content = "Selected optimization..."
# - context.domain = "performance_optimization"


from contextcore.telemetry import InsightEmitter

class AgentAnalyzer:
    def __init__(self):
        self.emitter = InsightEmitter()
        
    def analyze_data(self, data, task_id):
        # Analysis logic here
        confidence = self.calculate_confidence(results)
        
        # Legacy emission
        self.emitter.emit_insight({
            "agent.id": "data-analyzer",
            "agent.type": "llm",
            "insight.type": "analysis",
            "insight.confidence": confidence,
            "task.id": task_id,
            "task.status": "completed"
        })


from contextcore.insights import InsightsAPI

class AgentAnalyzer:
    def __init__(self):
        self.insights = InsightsAPI()
        
    def analyze_data(self, data, task_id):
        # Analysis logic here
        confidence = self.calculate_confidence(results)
        
        # Modern API with OTel attributes
        self.insights.emit_agent_insight(
            agent_id="data-analyzer",
            agent_type="llm",
            insight_type="analysis",
            confidence=confidence,
            content="Analysis completed successfully",
            custom_attributes={
                "analysis.method": "statistical",
                "data.size": len(data)
            }
        )
        
        # Update task status separately
        self.insights.emit_task_update(
            task_id=task_id,
            status="completed",
            duration_ms=execution_time * 1000
        )


import opentelemetry.trace as trace
from contextcore.telemetry import InsightEmitter

tracer = trace.get_tracer(__name__)
emitter = InsightEmitter()

def custom_processing():
    with tracer.start_as_current_span("custom_process") as span:
        # Custom logic
        emitter.emit_insight({
            "agent.id": "custom-processor",
            "custom.metric": "processing_time",
            "custom.value": processing_time
        })


from contextcore.insights import InsightsAPI
from contextcore.tracing import ContextCoreTracer

insights = InsightsAPI()
tracer = ContextCoreTracer(__name__)

def custom_processing():
    with tracer.start_span("custom_process") as span:
        # Custom logic with enhanced context
        insights.emit_agent_insight(
            agent_id="custom-processor",
            insight_type="processing",
            custom_attributes={
                "processing.time_ms": processing_time * 1000,
                "processing.method": "parallel",
                "gen_ai.operation.name": "custom_process"
            }
        )
        
        # Automatically links to current span
        span.set_attribute("gen_ai.agent.id", "custom-processor")


def process_batch(items):
    for item in items:
        emitter.emit_insight({
            "agent.id": "batch-processor", 
            "item.id": item.id,
            "task.status": "processing"
        })


def process_batch(items):
    with insights.batch_context():
        for item in items:
            insights.emit_task_update(
                task_id=f"batch-{item.id}",
                agent_id="batch-processor",
                status="processing",
                custom_attributes={"batch.item_id": item.id}
            )
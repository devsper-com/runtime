"""Memory tools: store, search, list, delete, tag, summarize memory."""

from hivemind.tools.memory.store_memory import StoreMemoryTool
from hivemind.tools.memory.search_memory import SearchMemoryTool
from hivemind.tools.memory.list_memory import ListMemoryTool
from hivemind.tools.memory.delete_memory import DeleteMemoryTool
from hivemind.tools.memory.tag_memory import TagMemoryTool
from hivemind.tools.memory.summarize_memory import SummarizeMemoryTool
from hivemind.tools.registry import register

register(StoreMemoryTool())
register(SearchMemoryTool())
register(ListMemoryTool())
register(DeleteMemoryTool())
register(TagMemoryTool())
register(SummarizeMemoryTool())

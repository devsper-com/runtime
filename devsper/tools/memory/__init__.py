"""Memory tools: store, search, list, delete, tag, summarize memory."""

from devsper.tools.memory.store_memory import StoreMemoryTool
from devsper.tools.memory.search_memory import SearchMemoryTool
from devsper.tools.memory.list_memory import ListMemoryTool
from devsper.tools.memory.delete_memory import DeleteMemoryTool
from devsper.tools.memory.tag_memory import TagMemoryTool
from devsper.tools.memory.summarize_memory import SummarizeMemoryTool
from devsper.tools.registry import register

register(StoreMemoryTool())
register(SearchMemoryTool())
register(ListMemoryTool())
register(DeleteMemoryTool())
register(TagMemoryTool())
register(SummarizeMemoryTool())

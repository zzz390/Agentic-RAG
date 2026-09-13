'''
整个TextChunker就是把一篇长论文，切成大小合适、上下文完整、
无垃圾内容的小文本，用于后续向量化、存入数据库、RAG检索

总入口：chunk_paper
1.如果有章节，就走智能分块
 _chunk_by_sections
    _parse_sections解析各种各样的sections，全部变成字典形式
    _filter_sections过滤无效/垃圾章节
        _is_metadata_section检测垃圾标题
        _is_duplicate_abstract检测和摘要高度重复
        _is_metadata_content不看标题，检测垃圾内容
'''
import json
import logging
import re
from typing import Dict, List, Optional, Union

from src.schemas.indexing.models import ChunkMetadata, TextChunk

logger = logging.getLogger(__name__)


class TextChunker:
    def __init__(self, chunk_size: int = 600, overlap_size: int = 100, min_chunk_size: int = 100):
        self.chunk_size = chunk_size
        self.overlap_size = overlap_size
        self.min_chunk_size = min_chunk_size

        if overlap_size >= chunk_size:
            raise ValueError("Overlap size must be less than chunk size")

        logger.info(
            f"Text chunker initialized: chunk_size={chunk_size}, overlap_size={overlap_size}, min_chunk_size={min_chunk_size}"
        )

    #把输入的text字符串，分隔成一个单词列表
    def _split_into_words(self, text: str) -> List[str]:
        words = re.findall(r"\S+", text)
        #re.findall正则表达式模块的函数，找出所有匹配的字符串，返回一个列表
        #r"\S+"：\S匹配非空白字符，+：匹配前面的模式一次或多次
        #合起来就是匹配一段连续的非空白字符
        return words

    #把之前用 _split_into_words 分割好的单词列表，重新拼接成完整的文本字符串
    def _reconstruct_text(self, words: List[str]) -> str:
        return " ".join(words)

    #论文分块的总入口，决定用那种方式把论文切成小块
    def chunk_paper(
        self,
        title: str,
        abstract: str,
        full_text: str,
        arxiv_id: str,
        paper_id: str,
        sections: Optional[Union[Dict[str, str], str, list]] = None,
    ) -> List[TextChunk]:
        if sections:
        #如果有章节结构，就优先按章节分块
            try:
                section_chunks = self._chunk_by_sections(title, abstract, arxiv_id, paper_id, sections)
                if section_chunks:
                    logger.info(f"Created {len(section_chunks)} section-based chunks for {arxiv_id}")
                    return section_chunks
            except Exception as e:
                logger.warning(f"Section-based chunking failed for {arxiv_id}: {e}")

        logger.info(f"Using traditional word-based chunking for {arxiv_id}")
        return self.chunk_text(full_text, arxiv_id, paper_id)
        #调用普通分块方法，直接按单词数量切分，返回最终分块结果
        #优先按章节分块，失败或者没有章节，就降级用普通单词分块

    #最基础的按单词分块，把文本切成固定大小、带重叠的小块，用于向量检索
    def chunk_text(self, text: str, arxiv_id: str, paper_id: str) -> List[TextChunk]:
        if not text or not text.strip():
            logger.warning(f"Empty text provided for paper {arxiv_id}")
            return []

        words = self._split_into_words(text)

        if len(words) < self.min_chunk_size:
            logger.warning(f"Text for paper {arxiv_id} has only {len(words)} words, less than minimum {self.min_chunk_size}")
            if words:
                return [
                    TextChunk(
                        text=self._reconstruct_text(words),
                        metadata=ChunkMetadata(
                            chunk_index=0,
                            start_char=0,
                            end_char=len(text),
                            word_count=len(words),
                            overlap_with_previous=0,
                            overlap_with_next=0,
                        ),
                        arxiv_id=arxiv_id,
                        paper_id=paper_id,
                    )
                ]
            return []
        #如果文本太短了就不切分了，直接返回一个整块，如果没有单词，反回空列表

        chunks = []
        chunk_index = 0
        current_position = 0
        #chunks：存所有块，chunk_index：块编号（第0块、第1块…），current_position：当前切到第几个单词

        while current_position < len(words):
            chunk_start = current_position
            chunk_end = min(current_position + self.chunk_size, len(words))

            chunk_words = words[chunk_start:chunk_end]
            chunk_text = self._reconstruct_text(chunk_words)

            start_char = len(" ".join(words[:chunk_start])) if chunk_start > 0 else 0
            end_char = len(" ".join(words[:chunk_end]))
            #计算字符级起始位置

            overlap_with_previous = min(self.overlap_size, chunk_start) if chunk_start > 0 else 0
            overlap_with_next = self.overlap_size if chunk_end < len(words) else 0
            #计算块之间的重复单词数

            chunk = TextChunk(
                text=chunk_text,
                metadata=ChunkMetadata(
                    chunk_index=chunk_index,
                    start_char=start_char,
                    end_char=end_char,
                    word_count=len(chunk_words),
                    overlap_with_previous=overlap_with_previous,
                    overlap_with_next=overlap_with_next,
                    section_title=None,
                ),

                arxiv_id=arxiv_id,
                paper_id=paper_id,
            )
            chunks.append(chunk)
            # 创建一个文本块，存入块列表

            current_position += self.chunk_size - self.overlap_size
            chunk_index += 1

            if chunk_end >= len(words):
                break

        logger.info(f"Chunked paper {arxiv_id}: {len(words)} words -> {len(chunks)} chunks")

        return chunks

    #按照章节智能分块，根据论文章节大小，自动决定整块用、合并小章节、拆分大章节
    def _chunk_by_sections(
        self, title: str, abstract: str, arxiv_id: str, paper_id: str, sections: Union[Dict[str, str], str, list]
    ) -> List[TextChunk]:
        sections_dict = self._parse_sections(sections)
        #把传入的章节数据，统一解析成字典
        if not sections_dict:
            return []

        sections_dict = self._filter_sections(sections_dict, abstract)
        #过滤无用章节，去掉作者、邮箱、重复摘要、元数据等垃圾内容
        if not sections_dict:
            logger.warning(f"No meaningful sections found after filtering for {arxiv_id}")
            return []

        header = f"{title}\n\nAbstract: {abstract}\n\n"
        #创建头部信息，每一块都会带上标题+摘要

        chunks = []
        small_sections = []

        section_items = list(sections_dict.items())
        #把章节字典转成列表，方便遍历

        for i, (section_title, section_content) in enumerate(section_items):
            content_str = str(section_content) if section_content else ""
            section_words = len(content_str.split())

            #章节太短，小于100词，先攒起来，等待合并
            if section_words < 100:
                small_sections.append((section_title, content_str, section_words))

                if i == len(section_items) - 1 or len(str(section_items[i + 1][1]).split()) >= 100:
                    chunks.extend(self._create_combined_chunk(header, small_sections, chunks, arxiv_id, paper_id))
                    small_sections = []
                #如果已经到了最后一个章节、或者下一个章节是大章节，
                # 就调用_create_combined_chunk合并小章节，合并之后清空小章节缓存

            elif 100 <= section_words <= 800:
                chunk_text = f"{header}Section: {section_title}\n\n{content_str}"
                chunk = self._create_section_chunk(chunk_text, section_title, len(chunks), arxiv_id, paper_id)
                chunks.append(chunk)
            #如果大小在100-800之间，可以直接作为一个完整块，
            # 调用_create_section_chunk带上标题摘要和章节内容，一起拼成一个chunk

            else:
                section_text = f"Section: {section_title}\n\n{content_str}"
                full_section_text = f"{header}{section_text}"

                section_chunks = self._split_large_section(
                    full_section_text, header, section_title, len(chunks), arxiv_id, paper_id
                )
                chunks.extend(section_chunks)
            #如果章节太大，调用_split_large_section切成带上下文的小块
        return chunks

    #这个函数是章节格式统一器，不管是传入的格式是字典、列表还是JSON字符串，都解析为字典
    def _parse_sections(self, sections: Union[Dict[str, str], str, list]) -> Dict[str, str]:
        if isinstance(sections, dict):
            return sections
        #如果已经是字典了，就不管他

        elif isinstance(sections, list):
        #列表的处理方法
            result = {}
            for i, section in enumerate(sections):
                if isinstance(section, dict):
                #如果章节是字典
                    title = section.get("title", section.get("heading", f"Section {i + 1}"))
                    content = section.get("content", section.get("text", ""))
                    result[title] = content
                else:
                #如果章节只是普通字符串
                    result[f"Section {i + 1}"] = str(section)
            return result

        elif isinstance(sections, str):
        #JSON的处理方法
            try:
                parsed = json.loads(sections)
                if isinstance(parsed, dict):
                    return parsed
                elif isinstance(parsed, list):
                    result = {}
                    for i, section in enumerate(parsed):
                        if isinstance(section, dict):
                            title = section.get("title", section.get("heading", f"Section {i + 1}"))
                            content = section.get("content", section.get("text", ""))
                            result[title] = content
                        else:
                            result[f"Section {i + 1}"] = str(section)
                    return result
            except json.JSONDecodeError:
                logger.warning("Failed to parse sections JSON")
        return {}

    #把没用的章节（作者、邮箱、重复摘要、元数据）都删掉，只留下正文内容
    def _filter_sections(self, sections_dict: Dict[str, str], abstract: str) -> Dict[str, str]:
        filtered = {}
        abstract_words = set(abstract.lower().split())

        for section_title, section_content in sections_dict.items():
            content_str = str(section_content).strip()

            if not content_str:
                continue

            if self._is_metadata_section(section_title):
            #调用_is_metadata_section，如果是元数据章节，就删掉
                continue

            if self._is_duplicate_abstract(content_str, abstract, abstract_words):
            #调用_is_duplicate_abstract，要是内容和摘要高度重复，删掉
                logger.debug(f"Skipping duplicate abstract section: {section_title}")
                continue

            if len(content_str.split()) < 20 and self._is_metadata_content(content_str):
            #如果内容很短+是元数据，删掉
                logger.debug(f"Skipping metadata section: {section_title}")
                continue

            filtered[section_title] = content_str
            #以上都不触发，保留这个章节

        return filtered

    #章节检测器，用来判断一个章节是不是元数据（作者、邮箱等），是的话就过滤掉
    def _is_metadata_section(self, section_title: str) -> bool:
        title_lower = section_title.lower().strip()

        metadata_indicators = [
            "content",
            "header",
            "authors",
            "author",
            "affiliation",
            "email",
            "arxiv",
            "preprint",
            "submitted",
            "received",
            "accepted",
        ]

        if title_lower in metadata_indicators or len(title_lower) < 5:
            return True

        for indicator in metadata_indicators:
            if indicator in title_lower and len(title_lower) < 20:
                return True

        return False

    #内容重复检测器，专门判断章节内容是不是和摘要高度重复，如果是，就判定为重复，后面就过滤掉
    def _is_duplicate_abstract(self, content: str, abstract: str, abstract_words: set) -> bool:
        content_lower = content.lower().strip()
        abstract_lower = abstract.lower().strip()

        if abstract_lower in content_lower or content_lower in abstract_lower:
            return True

        content_words = set(content_lower.split())

        if len(abstract_words) > 10:
            overlap = len(abstract_words.intersection(content_words))
            overlap_ratio = overlap / len(abstract_words)

            if overlap_ratio > 0.8:
                return True

        return False


    #垃圾内容检测器，不看标题，只看内容里有没有邮箱、大学等，短文本里出现多个就判定为垃圾文本
    def _is_metadata_content(self, content: str) -> bool:
        content_lower = content.lower()

        metadata_patterns = [
            "@",
            "arxiv:",
            "university",
            "institute",
            "department",
            "college",
            "gmail.com",
            "edu",
            "ac.uk",
            "preprint",
        ]

        word_count = len(content.split())
        if word_count < 30:
            metadata_word_count = sum(1 for pattern in metadata_patterns if pattern in content_lower)
            if metadata_word_count >= 2:
                return True

        return False

    #小块合并器，把段章节合并成大小合适的块，如果实在太多，会合并到上一个块里面
    def _create_combined_chunk(
        self, header: str, small_sections: List, existing_chunks: List, arxiv_id: str, paper_id: str
    ) -> List[TextChunk]:
        if not small_sections:
            return []

        combined_content = []
        total_words = 0

        for section_title, content, word_count in small_sections:
            combined_content.append(f"Section: {section_title}\n\n{content}")
            total_words += word_count

        combined_text = f"{header}{'\n\n'.join(combined_content)}"

        if total_words + len(header.split()) < 200 and existing_chunks:
            prev_chunk = existing_chunks[-1]
            merged_text = f"{prev_chunk.text}\n\n{'\n\n'.join(combined_content)}"

            existing_chunks[-1] = TextChunk(
                text=merged_text,
                metadata=ChunkMetadata(
                    chunk_index=prev_chunk.metadata.chunk_index,
                    start_char=0,
                    end_char=len(merged_text),
                    word_count=len(merged_text.split()),
                    overlap_with_previous=0,
                    overlap_with_next=0,
                    section_title=f"{prev_chunk.metadata.section_title} + Combined",
                ),
                arxiv_id=arxiv_id,
                paper_id=paper_id,
            )
            return []

        sections_titles = [title for title, _, _ in small_sections]
        combined_title = " + ".join(sections_titles[:3])
        if len(sections_titles) > 3:
            combined_title += f" + {len(sections_titles) - 3} more"

        chunk = self._create_section_chunk(combined_text, combined_title, len(existing_chunks), arxiv_id, paper_id)
        return [chunk]

    #块生成工具，把准备好的文本、标题、编号打包成一个标准的TextChunk格式
    def _create_section_chunk(
        self, chunk_text: str, section_title: str, chunk_index: int, arxiv_id: str, paper_id: str
    ) -> TextChunk:
        return TextChunk(
            text=chunk_text,
            metadata=ChunkMetadata(
                chunk_index=chunk_index,
                start_char=0,
                end_char=len(chunk_text),
                word_count=len(chunk_text.split()),
                overlap_with_previous=0,
                overlap_with_next=0,
                section_title=section_title,
            ),
            arxiv_id=arxiv_id,
            paper_id=paper_id,
        )

    #大章节切割器，当一个章节太长时，先用普通滑动分块切开，再给每一小块都加上标题+摘要头部，保证每一块都有完整上下文
    def _split_large_section(
        self, full_section_text: str, header: str, section_title: str, base_chunk_index: int, arxiv_id: str, paper_id: str
    ) -> List[TextChunk]:
        section_only = full_section_text[len(header) :]

        traditional_chunks = self.chunk_text(section_only, arxiv_id, paper_id)

        enhanced_chunks = []
        for i, chunk in enumerate(traditional_chunks):
            enhanced_text = f"{header}{chunk.text}"

            enhanced_chunk = TextChunk(
                text=enhanced_text,
                metadata=ChunkMetadata(
                    chunk_index=base_chunk_index + i,
                    start_char=chunk.metadata.start_char,
                    end_char=chunk.metadata.end_char + len(header),
                    word_count=len(enhanced_text.split()),
                    overlap_with_previous=chunk.metadata.overlap_with_previous,
                    overlap_with_next=chunk.metadata.overlap_with_next,
                    section_title=f"{section_title} (Part {i + 1})",
                ),
                arxiv_id=arxiv_id,
                paper_id=paper_id,
            )
            enhanced_chunks.append(enhanced_chunk)

        return enhanced_chunks
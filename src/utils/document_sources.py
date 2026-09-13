"""为 arXiv 论文与用户上传文档构建引用/来源 URL。"""


def paper_source_url(arxiv_id: str) -> str:
    if not arxiv_id:
        return ""
    if arxiv_id.startswith("upload-"):
        return f"upload://{arxiv_id}"
    arxiv_id_clean = arxiv_id.split("v")[0] if "v" in arxiv_id else arxiv_id
    return f"https://arxiv.org/pdf/{arxiv_id_clean}.pdf"

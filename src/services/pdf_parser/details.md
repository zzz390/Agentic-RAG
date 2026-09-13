## DoclingParser

- __init__配好docling的documentConverter（PDF 管线选项：是否做表格结构、是否 OCR），并记下 最大页数、最大文件体积
- _warm_up_models如果这篇论文还没有标记过，就把_warmed_up 设为 True，相当于进入解析之前打一次标记。
- _validate_pdf对本地PDF做安检：是否空文件、是否超过配置大小、问及那头是否是&PDF-，打开页数是否超过规定等。
- parse_pdf第一步先_validate_pdf检查PDF，然后_warm_up_models打标签，_converter.convert处理一个PDF，把这个PDF变成结构化数据。
- 然后一个一个章节遍历，当元素是 title 或 section_header 时，表示 当前章节结束、下一章节开始，此时把上一章节存入列表，
- 然后开始新一章节的处理，如果不是标题或者章节头，就当作正文，追加到当前章节的内容。最后返回处理完PDF的结构化数据PdfContent。

## Parser

- PDFParserService对DoclingParser 的 薄封装，主要解决两件事：异步接口+ 统一错误处理。

## Factory

- make_pdf_parser_service读取系统配置，构建一个PDFParserService。同时建缓存。

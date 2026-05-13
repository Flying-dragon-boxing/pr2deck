# pr2deck

从 GitHub Pull Request changelog 生成分页 HTML 演示稿。

`pr2deck` 从标准输入读取按类别分组的 PR 列表，拉取 GitHub PR 元信息，可选调用 OpenAI-compatible Chat API 生成适合卡片展示的短摘要，下载作者头像，并把完整 HTML deck 输出到标准输出。

## 功能

- 把 PR 列表转换成 16:9 HTML slide deck。
- 支持按 `Feature`、`Fix`、`Refactor` 等标题分组。
- 从 GitHub 获取 PR 标题、正文、作者和头像。
- 支持 OpenAI-compatible LLM API 生成短摘要。
- prompt 可放在 `prompt.txt`，也可通过环境变量指定其它文件。
- 本地缓存 GitHub 和 LLM 响应，减少重复请求。

## 安装

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 输入格式

准备一个类似 `changelog.txt` 的文件：

```text
Feature
Feature: add class PotXC_FDM and Pot_Cosikr by @linpeize in #6962
[Feature] Add gemv_op_mt for DSP by @Cstandardlib in #7009

Fix
Fix: correct the unit conversion between Plumed and ASE in example by @kirk0830 in #6993
```

不含 PR 编号的行会作为分组标题；包含 `#1234` 的行会被识别为 PR 条目。

## 使用

```bash
python pr2deck.py < changelog.txt > index.html
```

也可以使用构建脚本：

```bash
./build.sh
```

```powershell
.\build.ps1
```

## 环境变量

| 变量 | 说明 |
| --- | --- |
| `GITHUB_REPO` | GitHub 仓库，格式为 `owner/name`。默认是 `deepmodeling/abacus-develop`。 |
| `GITHUB_TOKEN` | 可选 GitHub token，用于提高 API rate limit。 |
| `LLM_API_BASE_URL` | OpenAI-compatible Chat API 地址，例如 `https://api.deepseek.com`。 |
| `LLM_API_KEY` | LLM 服务的 API key。 |
| `LLM_MODEL` | 模型名，例如 `deepseek-chat`。默认是 `deepseek-chat`。 |
| `PR2DECK_PROMPT_FILE` | prompt 文件路径。默认是 `prompt.txt`。 |
| `PR_CACHE_FILE` | GitHub PR 缓存文件。默认是 `.pr_cache.json`。 |
| `PR_CACHE_TTL` | GitHub PR 缓存时间，单位秒。默认是 `86400`。 |
| `MODEL_CACHE_FILE` | LLM 响应缓存文件。默认是 `.model_cache.json`。 |
| `MODEL_CACHE_TTL` | LLM 响应缓存时间，单位秒。默认是 `604800`。 |

如果 `LLM_API_KEY` 为空，程序不会调用模型，会退回到使用 PR body 文本。

## Prompt

默认 prompt 在 `prompt.txt`。可以直接修改这个文件，也可以指定其它 prompt：

```bash
export PR2DECK_PROMPT_FILE=my_prompt.txt
python pr2deck.py < changelog.txt > index.html
```

## 命令行参数

```bash
python pr2deck.py --help
```

常用参数：

- `--refresh-cache`：重新从 GitHub 拉取 PR 信息。
- `--refresh-model-cache`：重新生成 LLM 摘要。
- `--clear-cache`：删除本地 PR 缓存和模型缓存。
- `--title "My Changelog"`：设置 HTML 文档标题。

## 注意

生成的 HTML 文件默认被 Git 忽略。生产环境的 key 不应提交到仓库，建议通过本地脚本或环境变量管理。

## 许可证

本项目采用 BSD 3-Clause License，详见 [LICENSE](LICENSE)。

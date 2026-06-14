# AI Research Notes

## Transformer Architecture Overview

The Transformer architecture, introduced in the paper "Attention Is All You Need" (Vaswani et al., 2017),
has become the foundation of modern large language models (LLMs).

### Key Components

- **Self-Attention Mechanism**: Computes weighted representations of input sequences
  - Query (Q), Key (K), Value (V) projections
  - Scaled dot-product attention: `Attention(Q,K,V) = softmax(QK^T / sqrt(d_k)) * V`
  
- **Multi-Head Attention**: Runs multiple attention operations in parallel
  - Allows the model to focus on different representation subspaces
  - Typically 8-16 heads in practice

- **Position Encoding**: Injects sequence order information
  - Sinusoidal encoding (original paper)
  - Learned position embeddings (GPT-style)
  - Rotary Position Embedding (RoPE) - used in LLaMA, Qwen

## Model Scaling Laws

Research by Kaplan et al. (2020) and Hoffmann et al. (2022) established scaling laws:

| Parameter | Kaplan Scaling | Chinchilla Scaling |
|-----------|---------------|-------------------|
| Model Size (N) | N^0.076 | N^0.50 |
| Data Size (D) | D^0.095 | D^0.50 |
| Compute (C) | C^0.057 | C^0.33 |
| Optimal D/N | ~1:1 | ~20:1 (tokens:params) |

### Chinchilla Optimal

For a model with N parameters, the optimal training tokens D ≈ 20N.
This means:
- 7B model → ~140B tokens optimal
- 70B model → ~1.4T tokens optimal

## Fine-tuning Approaches

### Supervised Fine-Tuning (SFT)
Training on instruction-response pairs to align model behavior.

### RLHF (Reinforcement Learning from Human Feedback)
1. Train reward model on human preferences
2. Optimize policy using PPO
3. Iterate with new preference data

### DPO (Direct Preference Optimization)
Simplifies RLHF by directly optimizing from preference pairs
without explicit reward modeling. More stable and computationally
efficient than PPO-based RLHF.

## RAG (Retrieval-Augmented Generation)

RAG combines retrieval systems with generative models:

1. **Indexing**: Documents → chunks → embeddings → vector database
2. **Retrieval**: Query embedding → similarity search → top-K chunks
3. **Generation**: Prompt + retrieved context → LLM → answer

### Advanced RAG Techniques

- **HyDE**: Generate hypothetical answer first, then search
- **Self-RAG**: Model decides when to retrieve and evaluates relevance
- **Graph RAG**: Combines knowledge graphs with vector search
- **Agentic RAG**: Multi-step retrieval with tool use

## Open Source Models (2024-2025)

### Top Chinese Models
- **Qwen 2.5** (Alibaba): 0.5B to 72B parameters
- **DeepSeek V3**: MoE architecture, 671B total / 37B active
- **Yi** (01.AI): Strong bilingual performance
- **GLM-4** (Zhipu): Competitive on Chinese benchmarks

### Key Trends
1. Mixture of Experts (MoE) becoming standard
2. Long context windows (128K-1M tokens)
3. Multimodal capabilities (text + image + code)
4. Reducing inference costs through quantization

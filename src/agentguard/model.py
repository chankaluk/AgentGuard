from __future__ import annotations

import math

import torch
from torch import nn


class ExplainableTransformerBlock(nn.Module):
    def __init__(self, d_model: int, n_heads: int, dim_feedforward: int, dropout: float):
        super().__init__()
        self.norm1 = nn.LayerNorm(d_model)
        self.attention = nn.MultiheadAttention(
            d_model, n_heads, dropout=dropout, batch_first=True
        )
        self.norm2 = nn.LayerNorm(d_model)
        self.feedforward = nn.Sequential(
            nn.Linear(d_model, dim_feedforward),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(dim_feedforward, d_model),
            nn.Dropout(dropout),
        )

    def forward(self, x: torch.Tensor, padding_mask: torch.Tensor):
        normalized = self.norm1(x)
        attended, weights = self.attention(
            normalized,
            normalized,
            normalized,
            key_padding_mask=padding_mask,
            need_weights=True,
            average_attn_weights=False,
        )
        x = x + attended
        x = x + self.feedforward(self.norm2(x))
        return x, weights


class AgentBehaviorTransformer(nn.Module):
    def __init__(
        self,
        vocab_size: int,
        window_size: int,
        d_model: int = 64,
        n_heads: int = 4,
        n_layers: int = 2,
        dim_feedforward: int = 128,
        dropout: float = 0.1,
        numeric_features: int = 6,
    ):
        super().__init__()
        self.window_size = window_size
        self.d_model = d_model
        self.token_embedding = nn.Embedding(vocab_size, d_model, padding_idx=0)
        self.feature_projection = nn.Sequential(
            nn.Linear(numeric_features, d_model), nn.LayerNorm(d_model)
        )
        self.cls_embedding = nn.Parameter(torch.empty(1, 1, d_model))
        self.position_embedding = nn.Parameter(torch.empty(1, window_size + 1, d_model))
        self.input_dropout = nn.Dropout(dropout)
        self.blocks = nn.ModuleList(
            [
                ExplainableTransformerBlock(
                    d_model, n_heads, dim_feedforward, dropout
                )
                for _ in range(n_layers)
            ]
        )
        self.final_norm = nn.LayerNorm(d_model)
        self.classifier = nn.Sequential(
            nn.Linear(d_model, d_model // 2),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(d_model // 2, 1),
        )
        self.next_event_head = nn.Linear(d_model, vocab_size)
        self.reset_parameters()

    def reset_parameters(self) -> None:
        nn.init.normal_(self.cls_embedding, std=0.02)
        nn.init.normal_(self.position_embedding, std=0.02)

    def forward(
        self,
        tokens: torch.Tensor,
        features: torch.Tensor,
        mask: torch.Tensor,
        return_attention: bool = False,
    ) -> dict[str, torch.Tensor | list[torch.Tensor]]:
        batch_size, sequence_length = tokens.shape
        embedded = self.token_embedding(tokens) * math.sqrt(self.d_model)
        embedded = embedded + self.feature_projection(features)
        cls = self.cls_embedding.expand(batch_size, -1, -1)
        hidden = torch.cat([cls, embedded], dim=1)
        hidden = self.input_dropout(hidden + self.position_embedding[:, : sequence_length + 1])
        cls_mask = torch.ones((batch_size, 1), dtype=torch.bool, device=mask.device)
        full_mask = torch.cat([cls_mask, mask], dim=1)
        padding_mask = ~full_mask
        attentions = []
        for block in self.blocks:
            hidden, weights = block(hidden, padding_mask)
            if return_attention:
                attentions.append(weights)
        hidden = self.final_norm(hidden)
        logits = self.classifier(hidden[:, 0]).squeeze(-1)
        next_event_logits = self.next_event_head(hidden[:, 1:])
        result: dict[str, torch.Tensor | list[torch.Tensor]] = {
            "logits": logits,
            "next_event_logits": next_event_logits,
            "hidden": hidden,
        }
        if return_attention:
            result["attentions"] = attentions
        return result


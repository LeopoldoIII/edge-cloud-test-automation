"""Synthesizer for edge file packages, chunked streams, and corrupted mutation datasets."""

import os
import random
from dataclasses import dataclass

from src.core.crypto_integrity import CryptoIntegrityManager


@dataclass
class EdgeFileChunk:
    """Represents a single chunk of a multi-part file upload from an edge device."""

    file_id: str
    chunk_index: int
    total_chunks: int
    chunk_bytes: bytes
    chunk_sha256: str
    is_last: bool


class EdgeFileGenerator:
    """Constructs valid and mutated synthetic file packages for upload testing."""

    @staticmethod
    def create_binary_package(size_bytes: int = 1024 * 1024, pattern: bytes | None = None) -> bytes:
        """Creates a deterministic or pseudo-random binary payload.

        Args:
            size_bytes: Total size in bytes.
            pattern: Optional repeating byte pattern.

        Returns:
            Bytes buffer.
        """
        if pattern:
            repeats = (size_bytes // len(pattern)) + 1
            return (pattern * repeats)[:size_bytes]
        return os.urandom(size_bytes)

    @staticmethod
    def chunk_payload(
        file_id: str,
        data: bytes,
        chunk_size: int = 256 * 1024,
    ) -> list[EdgeFileChunk]:
        """Splits raw payload bytes into sequential EdgeFileChunk instances.

        Args:
            file_id: Unique file identifier.
            data: Raw payload bytes.
            chunk_size: Maximum size per chunk in bytes.

        Returns:
            Ordered list of EdgeFileChunk objects.
        """
        total_size = len(data)
        total_chunks = max(1, (total_size + chunk_size - 1) // chunk_size)
        chunks: list[EdgeFileChunk] = []

        for index in range(total_chunks):
            start = index * chunk_size
            end = min(start + chunk_size, total_size)
            chunk_data = data[start:end]
            chunk_hash = CryptoIntegrityManager.compute_sha256(chunk_data)
            is_last = index == total_chunks - 1

            chunks.append(
                EdgeFileChunk(
                    file_id=file_id,
                    chunk_index=index,
                    total_chunks=total_chunks,
                    chunk_bytes=chunk_data,
                    chunk_sha256=chunk_hash,
                    is_last=is_last,
                )
            )

        return chunks

    @staticmethod
    def mutate_corrupt_bytes(data: bytes, mutation_rate: float = 0.05) -> bytes:
        """Mutates a percentage of bytes in the payload to simulate bit-flip corruption.

        Args:
            data: Original raw bytes.
            mutation_rate: Fraction of bytes to mutate.

        Returns:
            Corrupted bytes buffer.
        """
        byte_array = bytearray(data)
        flips = max(1, int(len(data) * mutation_rate))
        indices = random.sample(range(len(data)), flips)
        for idx in indices:
            byte_array[idx] = byte_array[idx] ^ 0xFF
        return bytes(byte_array)

    @classmethod
    def generate_out_of_order_stream(
        cls,
        file_id: str,
        data: bytes,
        chunk_size: int = 128 * 1024,
    ) -> list[EdgeFileChunk]:
        """Creates valid chunks but shuffles their presentation order.

        Args:
            file_id: Unique file identifier.
            data: Raw payload bytes.
            chunk_size: Maximum chunk size in bytes.

        Returns:
            Shuffled list of EdgeFileChunk objects.
        """
        chunks = cls.chunk_payload(file_id, data, chunk_size)
        shuffled = list(chunks)
        random.shuffle(shuffled)
        return shuffled

    @classmethod
    def generate_partial_stream(
        cls,
        file_id: str,
        data: bytes,
        chunk_size: int = 128 * 1024,
        drop_last_n: int = 1,
    ) -> list[EdgeFileChunk]:
        """Creates chunks with the trailing chunks omitted to simulate premature disconnection.

        Args:
            file_id: Unique file identifier.
            data: Raw payload bytes.
            chunk_size: Maximum chunk size.
            drop_last_n: Number of final chunks to truncate.

        Returns:
            Truncated list of EdgeFileChunk objects.
        """
        chunks = cls.chunk_payload(file_id, data, chunk_size)
        cutoff = max(1, len(chunks) - drop_last_n)
        return chunks[:cutoff]

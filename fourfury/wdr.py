from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from ._utils import atomic_write
from .model import ModelAabb, ModelAsset, ModelBoundingSphere
from .rsc import Rsc5Resource
from .shaders import WdrShaderPreset, WdrShaderProgram
from .wtd import Rsc5Texture, Rsc5TextureDictionary
from ._wdr_constants import (
    WDR_DRAWABLE_SIZE,
    WDR_GEOMETRY_SIZE,
    WDR_INDEX_BUFFER_SIZE,
    WDR_LIGHT_SIZE,
    WDR_LOD_SIZE,
    WDR_MODEL_SIZE,
    WDR_RESOURCE_VERSION,
    WDR_SHADER_PARAMETER_NAMES,
    WDR_SHADER_SIZE,
    WDR_VERTEX_BUFFER_SIZE,
    WDR_VERTEX_LAYOUT_SIZE,
)
from ._wdr_geometry import (
    WdrDrawableLod,
    WdrDrawableModel,
    WdrGeometry,
    WdrIndexBuffer,
    WdrLodLevel,
    WdrPrimitiveType,
    WdrVertex,
    WdrVertexBuffer,
    WdrVertexElement,
    WdrVertexElementType,
    WdrVertexLayout,
    WdrVertexSemantic,
)
from ._wdr_material import (
    WdrShader,
    WdrShaderGroup,
    WdrShaderParameter,
    WdrTextureReference,
)
from ._wdr_math import WdrMatrix4, WdrVector2, WdrVector3, WdrVector4
from ._wdr_reader import _WdrReader as _WdrReaderBase
from ._wdr_scene import (
    WdrBone,
    WdrBoneFlags,
    WdrBoneId,
    WdrDrawable,
    WdrLight,
    WdrLightFlags,
    WdrLightType,
    WdrLightTypeFlags,
    WdrSkeleton,
    _texture_to_model,
)

try:
    from ._native import decode_wdr_vertices as _native_decode_wdr_vertices
except ImportError:
    _native_decode_wdr_vertices = None


class _WdrReader(_WdrReaderBase):
    """Compatibility façade whose decoder follows ``fourfury.wdr`` state."""

    def __init__(self, resource: Rsc5Resource) -> None:
        super().__init__(resource, lambda: _native_decode_wdr_vertices)


@dataclass(slots=True)
class WdrDocument:
    drawable: WdrDrawable
    resource: Rsc5Resource
    name: str = "drawable.wdr"
    source_path: str = ""

    @classmethod
    def from_path(cls, path: str | Path) -> "WdrDocument":
        source = Path(path)
        document = cls.from_bytes(source.read_bytes(), name=source.name)
        document.source_path = str(source)
        return document

    @classmethod
    def from_bytes(cls, data: bytes, *, name: str = "drawable.wdr") -> "WdrDocument":
        resource = Rsc5Resource.from_bytes(data)
        if resource.version != WDR_RESOURCE_VERSION:
            raise ValueError(f"unsupported WDR resource version: {resource.version:#x}")
        drawable = _WdrReader(resource).parse_drawable()
        return cls(drawable, resource, name)

    @property
    def lods(self) -> tuple[WdrDrawableLod | None, ...]:
        return self.drawable.lods

    @property
    def models(self) -> tuple[WdrDrawableModel, ...]:
        return self.drawable.models

    @property
    def geometries(self) -> tuple[WdrGeometry, ...]:
        return self.drawable.geometries

    @property
    def shaders(self) -> tuple[WdrShader, ...]:
        group = self.drawable.shader_group
        return () if group is None else group.shaders

    @property
    def unknown_shaders(self) -> tuple[WdrShader, ...]:
        return tuple(shader for shader in self.shaders if not shader.is_known)

    def find_shaders(
        self,
        value: str | int | WdrShaderPreset | WdrShaderProgram,
    ) -> tuple[WdrShader, ...]:
        """Find material instances by hash, program, preset, or stored name."""

        if isinstance(value, int):
            return tuple(
                shader for shader in self.shaders if shader.name_hash == value
            )
        if isinstance(value, WdrShaderPreset):
            return tuple(shader for shader in self.shaders if shader.preset is value)
        if isinstance(value, WdrShaderProgram):
            return tuple(shader for shader in self.shaders if shader.program is value)
        key = str(value).casefold()
        return tuple(
            shader
            for shader in self.shaders
            if key
            in {
                shader.name.casefold(),
                shader.file_name.casefold(),
                Path(shader.file_name).stem.casefold(),
            }
        )

    @property
    def embedded_texture_dictionary(self) -> Rsc5TextureDictionary | None:
        group = self.drawable.shader_group
        return None if group is None else group.texture_dictionary

    @property
    def embedded_textures(self) -> tuple[Rsc5Texture, ...]:
        dictionary = self.embedded_texture_dictionary
        return () if dictionary is None else dictionary.textures

    def find_embedded_texture(self, name: str) -> Rsc5Texture | None:
        dictionary = self.embedded_texture_dictionary
        return None if dictionary is None else dictionary.get(name)

    def to_model(self) -> ModelAsset:
        """Project this drawable into FourFury's target-independent model contract."""

        drawable = self.drawable
        has_skeleton = drawable.skeleton is not None
        lods = tuple(
            lod.to_model_lod(
                draw_bucket_mask=drawable.draw_bucket_masks[index],
                has_skeleton=has_skeleton,
            )
            for index, lod in enumerate(drawable.lods)
            if lod is not None
        )
        return ModelAsset(
            name=Path(self.name).stem,
            lods=lods,
            materials=tuple(
                shader.to_model_material(index=index)
                for index, shader in enumerate(self.shaders)
            ),
            textures=tuple(
                _texture_to_model(texture) for texture in self.embedded_textures
            ),
            skeleton=(
                None
                if drawable.skeleton is None
                else drawable.skeleton.to_model_skeleton()
            ),
            lights=tuple(light.to_model_light() for light in drawable.lights),
            bounding_box=ModelAabb(
                minimum=(
                    drawable.bounding_box_minimum.x,
                    drawable.bounding_box_minimum.y,
                    drawable.bounding_box_minimum.z,
                ),
                maximum=(
                    drawable.bounding_box_maximum.x,
                    drawable.bounding_box_maximum.y,
                    drawable.bounding_box_maximum.z,
                ),
            ),
            bounding_sphere=ModelBoundingSphere(
                center=(
                    drawable.bounding_center.x,
                    drawable.bounding_center.y,
                    drawable.bounding_center.z,
                ),
                radius=drawable.bounding_sphere_radius,
            ),
            source_path=self.source_path,
        )

    def to_bytes(self) -> bytes:
        """Return the original lossless RSC5 resource.

        WDR structures are currently a read-only semantic view. Fixed-size binary
        editing will be added once every drawable extension field is identified.
        """

        return self.resource.to_bytes()

    def save(self, path: str | Path) -> None:
        atomic_write(path, self.to_bytes())


def load_wdr(source: str | Path | bytes | BinaryIO) -> WdrDocument:
    if isinstance(source, (str, Path)):
        return WdrDocument.from_path(source)
    if isinstance(source, bytes):
        return WdrDocument.from_bytes(source)
    return WdrDocument.from_bytes(source.read())


__all__ = [
    "WDR_DRAWABLE_SIZE", "WDR_GEOMETRY_SIZE", "WDR_INDEX_BUFFER_SIZE", "WDR_LIGHT_SIZE",
    "WDR_LOD_SIZE", "WDR_MODEL_SIZE", "WDR_RESOURCE_VERSION", "WDR_SHADER_PARAMETER_NAMES",
    "WDR_SHADER_SIZE", "WDR_VERTEX_BUFFER_SIZE", "WDR_VERTEX_LAYOUT_SIZE", "WdrBone",
    "WdrBoneFlags", "WdrBoneId", "WdrDocument", "WdrDrawable", "WdrDrawableLod", "WdrDrawableModel",
    "WdrGeometry", "WdrIndexBuffer", "WdrLight", "WdrLightFlags", "WdrLightType",
    "WdrLightTypeFlags", "WdrLodLevel",
    "WdrPrimitiveType", "WdrShader", "WdrShaderGroup", "WdrShaderParameter", "WdrSkeleton",
    "WdrMatrix4", "WdrTextureReference", "WdrVector2", "WdrVector3", "WdrVector4", "WdrVertex",
    "WdrVertexBuffer", "WdrVertexElement", "WdrVertexElementType", "WdrVertexLayout",
    "WdrVertexSemantic", "load_wdr",
]


# These classes remain public members of ``fourfury.wdr`` even though their
# implementations live in focused internal modules. Keeping the original module
# identity preserves reprs and pickle compatibility for callers.
for _public_name in __all__:
    _public_value = globals().get(_public_name)
    if (
        isinstance(_public_value, type)
        and _public_value.__module__.startswith("fourfury._wdr_")
    ):
        _public_value.__module__ = __name__
del _public_name, _public_value

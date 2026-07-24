from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..animation import UvTransform
from ..model import (
    ModelMaterial,
    ModelMaterialParameter,
    ModelParameterKind,
    ModelTextureReference,
)
from ..shaders import (
    WdrShaderDefinition,
    WdrShaderParameterName,
    WdrShaderPreset,
    WdrShaderProgram,
    find_wdr_shader_definition,
    find_wdr_shader_program,
)
from ..wtd import Rsc5TextureDictionary
from .constants import WDR_SHADER_PARAMETER_NAMES
from .math import WdrVector4


@dataclass(frozen=True, slots=True)
class WdrTextureReference:
    file_name: str
    name: str
    _pointer: int = field(repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class WdrShaderParameter:
    name_hash: int
    parameter_type: int
    texture: WdrTextureReference | None = None
    value: WdrVector4 | tuple[WdrVector4, ...] | None = None

    @property
    def name(self) -> str:
        return WDR_SHADER_PARAMETER_NAMES.get(self.name_hash, f"hash_{self.name_hash:08x}")

    @property
    def known_name(self) -> WdrShaderParameterName | None:
        name = WDR_SHADER_PARAMETER_NAMES.get(self.name_hash)
        return None if name is None else WdrShaderParameterName(name)

    @property
    def is_texture(self) -> bool:
        return self.parameter_type == 0

    def to_model_parameter(self) -> ModelMaterialParameter:
        """Project this RAGE parameter into the neutral model contract."""

        texture = (
            None
            if self.texture is None
            else ModelTextureReference(self.texture.name, self.texture.file_name)
        )
        if isinstance(self.value, WdrVector4):
            value = tuple(self.value)
        elif self.value is not None:
            value = tuple(tuple(item) for item in self.value)
        else:
            value = None
        return ModelMaterialParameter(
            name_hash=self.name_hash,
            kind=ModelParameterKind.TEXTURE
            if self.is_texture
            else ModelParameterKind.VALUE,
            name=WDR_SHADER_PARAMETER_NAMES.get(self.name_hash),
            value=value,
            texture=texture,
        )


@dataclass(slots=True)
class WdrShader:
    name: str
    file_name: str
    name_hash: int
    block_map_address: int
    version: int
    draw_bucket: int
    usage_count: int
    shader_index: int
    parameters: tuple[WdrShaderParameter, ...]
    reserved: tuple[int, ...]
    _pointer: int = field(repr=False, compare=False)

    @property
    def program(self) -> WdrShaderProgram | None:
        """Return the typed compiled program when it is in the stock catalog."""

        program = find_wdr_shader_program(self.name)
        if program is not None:
            return program
        definition = self.definition
        return None if definition is None else definition.program

    @property
    def preset(self) -> WdrShaderPreset | None:
        """Return the typed SPS material preset selected by this material."""

        definition = self.definition
        return None if definition is None else definition.preset

    @property
    def definition(self) -> WdrShaderDefinition | None:
        """Resolve the stock SPS definition, preferring the stored file name."""

        return find_wdr_shader_definition(
            self.file_name
        ) or find_wdr_shader_definition(self.name)

    @property
    def is_known(self) -> bool:
        return self.program is not None or self.definition is not None

    @property
    def unknown_parameters(self) -> tuple[WdrShaderParameter, ...]:
        return tuple(
            parameter
            for parameter in self.parameters
            if parameter.known_name is None
        )

    def get_parameter(
        self, value: str | int | WdrShaderParameterName
    ) -> WdrShaderParameter | None:
        """Find a material parameter by hash, semantic name, or typed name."""

        if isinstance(value, int):
            return next(
                (
                    parameter
                    for parameter in self.parameters
                    if parameter.name_hash == value
                ),
                None,
            )
        key = str(value).casefold()
        return next(
            (
                parameter
                for parameter in self.parameters
                if parameter.name.casefold() == key
            ),
            None,
        )

    @property
    def has_uv_transform_parameters(self) -> bool:
        return any(
            self.get_parameter(name) is not None
            for name in (
                WdrShaderParameterName.GLOBAL_ANIMATION_UV_0,
                WdrShaderParameterName.GLOBAL_ANIMATION_UV_1,
            )
        )

    @property
    def uv_transform(self) -> UvTransform | None:
        """Return the material's two default UV-animation matrix rows."""

        row_u_parameter = self.get_parameter(
            WdrShaderParameterName.GLOBAL_ANIMATION_UV_0
        )
        row_v_parameter = self.get_parameter(
            WdrShaderParameterName.GLOBAL_ANIMATION_UV_1
        )
        if row_u_parameter is None and row_v_parameter is None:
            return None

        def row(
            parameter: WdrShaderParameter | None,
            default: tuple[float, float, float, float],
            name: str,
        ) -> tuple[float, float, float, float]:
            if parameter is None:
                return default
            if not isinstance(parameter.value, WdrVector4):
                raise ValueError(f"WDR {name} parameter is not a float4 value")
            return tuple(parameter.value)

        identity = UvTransform.identity()
        return UvTransform(
            row(row_u_parameter, identity.row_u, "global_animation_uv_0"),
            row(row_v_parameter, identity.row_v, "global_animation_uv_1"),
        )

    def to_model_material(self, *, index: int | None = None) -> ModelMaterial:
        """Return a target-format-independent material description."""

        material_index = self.shader_index if index is None else int(index)
        name = self.name or Path(self.file_name).stem or f"material_{material_index}"
        return ModelMaterial(
            index=material_index,
            name=name,
            shader_name=self.name,
            shader_file=self.file_name,
            render_bucket=self.draw_bucket,
            parameters=tuple(
                parameter.to_model_parameter() for parameter in self.parameters
            ),
            shader_hash=self.name_hash,
        )


@dataclass(slots=True)
class WdrShaderGroup:
    shaders: tuple[WdrShader, ...]
    texture_dictionary_pointer: int
    vertex_declaration_usage_flags: tuple[int, ...]
    reserved: tuple[int, int, int, int, int, int, int, int, int, int, int, int]
    reserved_data: tuple[int, ...]
    texture_dictionary: Rsc5TextureDictionary | None = field(repr=False, compare=False)
    _pointer: int = field(repr=False, compare=False)


__all__ = [
    "WdrTextureReference",
    "WdrShaderParameter",
    "WdrShader",
    "WdrShaderGroup",
]

"""Precompiled-code discretization execution engine."""

from __future__ import division

__copyright__ = "Copyright (C) 2007 Andreas Kloeckner"

__license__ = """
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see U{http://www.gnu.org/licenses/}.
"""




import numpy
import numpy.linalg as la
import pyublas
import hedge.discretization
import hedge.optemplate
import pymbolic.mapper
import hedge._internal as _internal
import hedge.backends.cpu_base
from pytools import monkeypatch_method




# precompiled flux building block debug monkeypatches -------------------------
@monkeypatch_method(_internal.ConstantFlux)
def __repr__(self):
    return str(self.value)
@monkeypatch_method(_internal.NormalFlux)
def __repr__(self):
    return "n[%d]" % self.axis
@monkeypatch_method(_internal.PenaltyFlux)
def __repr__(self):
    return "penalty(%s)" % self.power
@monkeypatch_method(_internal.SumFlux)
def __repr__(self):
    return "(%s+%s)" % (self.operand1, self.operand2)
@monkeypatch_method(_internal.ProductFlux)
def __repr__(self):
    return "(%s*%s)" % (self.operand1, self.operand2)
@monkeypatch_method(_internal.NegativeFlux)
def __repr__(self):
    return "-%s" % self.operand
@monkeypatch_method(_internal.ChainedFlux)
def __repr__(self):
    #return "ChainedFlux(%s)" % self.child
    return str(self.child)
@monkeypatch_method(_internal.IfPositiveFlux)
def __repr__(self):
    return "(If %s>0 then %s else %s)" % (self.criterion, self.then_part, self.else_part)





# flux compilation ------------------------------------------------------------
class _FluxCoefficientCompiler(pymbolic.mapper.RecursiveMapper):
    def handle_unsupported_expression(self, expr):
        if isinstance(expr, _internal.Flux):
            return expr
        else:
            pymbolic.mapper.RecursiveMapper.\
                    handle_unsupported_expression(self, expr)

    def map_constant(self, expr):
        return _internal.ConstantFlux(expr)

    def map_sum(self, expr):
        return reduce(lambda f1, f2: _internal.SumFlux(
                    _internal.ChainedFlux(f1), 
                    _internal.ChainedFlux(f2)),
                (self.rec(c) for c in expr.children))

    def map_product(self, expr):
        return reduce(
                lambda f1, f2: _internal.ProductFlux(
                    _internal.ChainedFlux(f1), 
                    _internal.ChainedFlux(f2)),
                (self.rec(c) for c in expr.children))

    def map_negation(self, expr):
        return _internal.NegativeFlux(_internal.ChainedFlux(self.rec(expr.child)))

    def map_power(self, expr):
        base = self.rec(expr.base)
        result = base

        chain_base = _internal.ChainedFlux(base)

        assert isinstance(expr.exponent, int)

        for i in range(1, expr.exponent):
            result = _internal.ProductFlux(_internal.ChainedFlux(result), chain_base)

        return result

    def map_normal(self, expr):
        return _internal.NormalFlux(expr.axis)

    def map_penalty_term(self, expr):
        return _internal.PenaltyFlux(expr.power)

    def map_if_positive(self, expr):
        return _internal.IfPositiveFlux(
                _internal.ChainedFlux(self.rec(expr.criterion)),
                _internal.ChainedFlux(self.rec(expr.then)),
                _internal.ChainedFlux(self.rec(expr.else_)),
                )




class _FluxOpCompileMapper(hedge.optemplate.FluxDecomposer):
    def __init__(self):
        self.coeff_comp = _FluxCoefficientCompiler()

    def compile_coefficient(self, coeff):
        from hedge.flux import Flux
        if isinstance(coeff, (_internal.Flux)) and not isinstance(coeff, Flux):
            return coeff
        else:
            return self.coeff_comp(coeff)




# exec mapper -----------------------------------------------------------------
class ExecutionMapper(hedge.backends.cpu_base.ExecutionMapper):
    # implementation stuff ----------------------------------------------------
    def scalar_inner_flux(self, int_coeff, ext_coeff, field, lift, out=None):
        if out is None:
            out = self.discr.volume_zeros()

        if isinstance(field, (int, float, complex)) and field == 0:
            return 0

        from hedge._internal import ChainedFlux

        for fg in self.discr.face_groups:
            fluxes_on_faces = numpy.zeros(
                    (fg.face_count*fg.face_length()*fg.element_count(),),
                    dtype=field.dtype)
            
            self.perform_double_sided_flux(fg, 
                    ChainedFlux(int_coeff), ChainedFlux(ext_coeff),
                    field, fluxes_on_faces)

            if lift:
                self.lift_flux(fg, fg.ldis_loc.lifting_matrix(),
                        fg.local_el_inverse_jacobians, fluxes_on_faces, out)
            else:
                self.lift_flux(fg, fg.ldis_loc.multi_face_mass_matrix(),
                        None, fluxes_on_faces, out)

        return out


    def scalar_bdry_flux(self, int_coeff, ext_coeff, field, bfield, tag, lift, out=None):
        if out is None:
            out = self.discr.volume_zeros()

        bdry = self.discr.get_boundary(tag)
        if not bdry.nodes:
            return 0

        from hedge._internal import \
                perform_single_sided_flux, ChainedFlux, ZeroVector, \
                lift_flux
        if isinstance(field, (int, float, complex)) and field == 0:
            field = ZeroVector()
            dtype = bfield.dtype
        else:
            dtype = field.dtype

        if isinstance(bfield, (int, float, complex)) and bfield == 0:
            bfield = ZeroVector()

        if bdry.nodes:
            for fg in bdry.face_groups:
                fluxes_on_faces = numpy.zeros(
                        (fg.face_count*fg.face_length()*fg.element_count(),),
                        dtype=dtype)

                perform_single_sided_flux(
                        fg, ChainedFlux(int_coeff), ChainedFlux(ext_coeff),
                        field, bfield, fluxes_on_faces)

                if lift:
                    lift_flux(fg, fg.ldis_loc.lifting_matrix(),
                            fg.local_el_inverse_jacobians, 
                            fluxes_on_faces, out)
                else:
                    lift_flux(fg, fg.ldis_loc.multi_face_mass_matrix(),
                            None, 
                            fluxes_on_faces, out)

        return out




    # entry points ------------------------------------------------------------
    def map_flux_coefficient(self, op, field_expr, out=None, lift=False):
        from hedge.optemplate import BoundaryPair

        if isinstance(field_expr, BoundaryPair):
            bp = field_expr
            return self.scalar_bdry_flux(
                    op.int_coeff, op.ext_coeff,
                    self.rec(bp.field), self.rec(bp.bfield), 
                    bp.tag, lift, out)
        else:
            field = self.rec(field_expr)
            return self.scalar_inner_flux(
                    op.int_coeff, op.ext_coeff,
                    field, lift, out)

    def map_lift_coefficient(self, op, field_expr, out=None):
        return self.map_flux_coefficient(op, field_expr, out, lift=True)





class CompiledOpTemplate:
    def __init__(self, discr, pp_optemplate):
        self.discr = discr
        self.pp_optemplate = pp_optemplate

    def __call__(self, **vars):
        return ExecutionMapper(vars, self.discr)(self.pp_optemplate)




class Discretization(hedge.discretization.Discretization):
    def compile(self, optemplate):
        from hedge.optemplate import \
                OperatorBinder, \
                InverseMassContractor, \
                BCToFluxRewriter

        from pymbolic.mapper.constant_folder import CommutativeConstantFoldingMapper

        result = (
                InverseMassContractor()(
                    CommutativeConstantFoldingMapper()(
                        _FluxOpCompileMapper()(
                            BCToFluxRewriter()(
                                OperatorBinder()(
                                    optemplate))))))

        return CompiledOpTemplate(self, result)

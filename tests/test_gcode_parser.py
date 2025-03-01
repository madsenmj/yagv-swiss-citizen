import pytest
from src.gcodeParser import GcodeParser
from src.gcodeParser import Segment

class Test_calc_string:
    def test_negative_string(self):
        parser = GcodeParser()
        assert not parser.is_calc_arg("-1.3")
    
    def test_inline_add(self):
        parser = GcodeParser()
        assert parser.is_calc_arg("1.3+.1")

    def test_inline_subtract(self):
        parser = GcodeParser()
        assert parser.is_calc_arg("-1.3-.1")

    def test_inline_multiply(self):
        parser = GcodeParser()
        assert parser.is_calc_arg("1.0*2.0")

    def test_inline_divide(self):
        parser = GcodeParser()
        assert parser.is_calc_arg("1.0/2.0")

    def test_calc_in_brackets(self):
        parser = GcodeParser()
        assert parser.is_calc_arg("[1.0/2.0]")
    
    def test_negative_outside_brackets(self):
        parser = GcodeParser()
        assert parser.is_calc_arg("-[1.0*2.0]")
    
    def test_correct_sum(self):
        parser = GcodeParser()
        assert pytest.approx(parser.parse_calc("1.3+.1")) == 1.4

    def test_correct_sum_brackets(self):
        parser = GcodeParser()
        assert pytest.approx(parser.parse_calc("[1.3+.1]")) == 1.4

    def test_correct_negative_mult(self):
        parser = GcodeParser()
        assert pytest.approx(parser.parse_calc("-[2.0*.5]")) == -1.0

    def test_is_not_variable_calc_line(self):
        parser = GcodeParser()
        assert not parser.is_variable_calc("#510=1.2")        

    def test_is_not_variable_calc_line_negative(self):
        parser = GcodeParser()
        assert not parser.is_variable_calc("#510=-1.2")

    def test_is_variable_calc_line_negative_brackets(self):
        parser = GcodeParser()
        assert parser.is_variable_calc("#510=[-1.2]")

class Test_G1:

    def test_parseline_reads(self):
        parser = GcodeParser()
        parser.line = "G1 X1.0"
        parser.lineNb = 1
        parser.parseLine()
        assert len(parser.model.segments) == 1
        segment = parser.model.segments[0]
        assert segment.coords['X'] == 1.0
        assert segment.type == 'G1'

    def test_parseline_reads_relative(self):
        parser = GcodeParser()
        parser.line = "G1 U1.0 V2.0 W-1.0"
        parser.lineNb = 1
        parser.parseLine()
        assert len(parser.model.segments) == 1
        segment = parser.model.segments[0]
        assert segment.coords['X'] == 1.0
        assert segment.coords['Y'] == 2.0
        assert segment.coords['Z'] == -1.0
        assert segment.type == 'G1'

    def test_parseline_reads_mashed(self):
        parser = GcodeParser()
        parser.line = "G1X1.0"
        parser.lineNb = 1
        parser.parseLine()
        assert len(parser.model.segments) == 1
        segment = parser.model.segments[0]
        assert segment.coords['X'] == 1.0
        assert segment.type == 'G1'
        
    def test_parseline_reads_multiple_axis(self):
        parser = GcodeParser()
        parser.line = "G1 X1.0 Y2.0"
        parser.lineNb = 1
        parser.parseLine()
        assert len(parser.model.segments) == 1
        segment = parser.model.segments[0]
        assert segment.coords['X'] == 1.0
        assert segment.coords['Y'] == 2.0
        assert segment.type == 'G1'

    def test_parseline_reads_multiple_axis_mushed(self):
        parser = GcodeParser()
        parser.line = "G1X1.0Y2.0Z-1.2"
        parser.lineNb = 1
        parser.parseLine()
        assert len(parser.model.segments) == 1
        segment = parser.model.segments[0]
        assert segment.coords['X'] == 1.0
        assert segment.coords['Y'] == 2.0
        assert segment.coords['Z'] == -1.2
        assert segment.type == 'G1'
    
    def test_parseline_reads_inline_calculations_sum(self):
        parser = GcodeParser()
        parser.line = "G1X-[1.0+.1]Y2.0Z-1.2"
        parser.lineNb = 1
        parser.parseLine()
        assert len(parser.model.segments) == 1
        segment = parser.model.segments[0]
        assert pytest.approx(segment.coords['X']) == -1.1

    def test_parseline_reads_sequence_of_lines(self):
        parser = GcodeParser()
        parser.line = "G1X1.0"
        parser.lineNb = 1
        parser.parseLine()
        parser.line = "Y-2.0"
        parser.lineNb = 2
        parser.parseLine()
        assert len(parser.model.segments) == 2
        position = parser.model.position
        assert position['X'] == 1.0
        assert position['Y'] == -2.0

    def test_parseline_reads_sequence_of_relativelines(self):
        parser = GcodeParser()
        lines = ["G1X1.0Y2.0Z-1.2", "G1U1.0V2.0W-1.2"]
        parser.parseCode(lines)
        assert len(parser.model.segments) == 2
        position = parser.model.position
        assert position['X'] == 2.0
        assert position['Y'] == 4.0
        assert position['Z'] == -2.4

    def test_applies_tool_to_segment_tool(self):
        parser = GcodeParser()
        lines = ["T100(COMMENT)","G1X1.0Y2.0Z-1.2", "T2100", "G1U1.0V2.0W-1.2"]
        parser.parseCode(lines)
        assert len(parser.model.segments) == 2
        assert parser.model.segments[0].tool == "T1"
        assert parser.model.segments[1].tool == "T21"

class Test_variables:
    def test_reads_814_from_lines(self):
        parser = GcodeParser()
        lines = ["#510=3.4","G1X#814Y#510", "G1U1.0V2.0W-1.2", "$0", "#814=0000002500"]
        parser.parseCode(lines)
        assert len(parser.model.segments) == 2
        position = parser.model.position
        assert position['X'] == 1.250
        assert position['Y'] == 5.4
        assert position['Z'] == -1.2

    def test_evaluates_negative_var(self):
        parser = GcodeParser()
        lines = ["#510=-3.4","G1X.1Y#510"]
        parser.parseCode(lines)
        position = parser.model.position
        assert pytest.approx(position['Y']) == -3.4

    def test_evaluates_var_calculation(self):
        parser = GcodeParser()
        lines = ["#510=3.4","G1X#814+.1Y#510", "$0", "#814=0000002500"]
        parser.parseCode(lines)
        position = parser.model.position
        assert pytest.approx(position['X']) == .35

    def test_updates_variable_calcs(self):
        parser = GcodeParser()
        lines = ["#510=3.4", "#510=[#510/2]","G1X#510+.1", "$0", "#814=0000002500"]
        parser.parseCode(lines)
        position = parser.model.position
        assert pytest.approx(position['X']) == 1.8

class Test_Segment_Classification:
    def test_counts_layers(self):
        parser = GcodeParser()
        lines = ["T100","G1X1.0Y2.0Z-1.2", "T2100", "G1U1.0V2.0W-1.2","G1U1.0", "T100","G1X1.0Y2.0Z-1.2","G1W1.0"]
        parser.parseCode(lines)
        parser.model.classifySegments()
        segments = parser.model.segments
        assert len(segments) == 5
        assert segments[0].layerIdx == 0
        assert segments[1].layerIdx == 1
        assert segments[2].layerIdx == 1
        assert segments[3].layerIdx == 2
        assert segments[4].layerIdx == 2
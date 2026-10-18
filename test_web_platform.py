"""Browser snapshot and victory handling without launching Chrome."""
from unittest import TestCase
from unittest.mock import Mock, patch

from Board import Board, GameLost
from run_control import StopRequested
from test_board_platform import build_platform
from web_platform import WebPlatform
from game_pacer import GamePacer


class TestWebPlatform(TestCase):
    @patch('Runner.RunControl')
    @patch('Runner.Board')
    @patch('web_platform.WebPlatform')
    def test_web_accepts_target_time_without_replacing_total_limit(self, platform_type, board_type, control_type):
        from Runner import main
        self.assertEqual(main(['--platform', 'web', '--target-seconds', '35', '--seconds', '399']), 0)
        self.assertEqual(platform_type.call_args.kwargs['target_seconds'], 35)
        self.assertEqual([call.args[0] for call in control_type.call_args_list], [60, 399])

    def test_web_target_spreads_flags_over_individual_clicks(self):
        platform = WebPlatform.__new__(WebPlatform)
        platform._rows, platform._cols = 2, 2
        platform.settle = 0
        platform.input_mode = 'events'
        platform.control = Mock()
        platform.driver = Mock()
        now, times = [0], []
        def wait(seconds):
            now[0] += seconds
        platform.control.wait.side_effect = wait
        platform.pacer = GamePacer(35, 4, platform.control, clock=lambda: now[0])
        cells = {key: 'square blank' for key in ['1_1', '1_2', '2_1', '2_2']}
        cells['0_0'] = 'square open0'  # hidden sentinel cells are not progress
        platform._snapshot = {'face': 'facesmile', 'cells': cells.copy()}
        def execute(script, positions, flag):
            self.assertEqual(len(positions), 1)
            times.append(now[0])
            row, col = positions[0]
            cells[f'{row + 1}_{col + 1}'] = 'square bombflagged'
            return {'face': 'facesmile', 'cells': cells.copy()}
        platform.driver.execute_script.side_effect = execute
        platform.flag_cells([(0, 0), (0, 1), (1, 0)])
        self.assertEqual(len(times), 3)
        self.assertTrue(all(0 < b - a <= 0.5 for a, b in zip(times, times[1:])))
        self.assertEqual(platform.pacer.progress, 3)

    def test_each_web_attempt_uses_current_control_and_resets_pacing(self):
        platform = WebPlatform.__new__(WebPlatform)
        platform._rows, platform._cols = 2, 2
        platform.target_seconds = 35
        platform.control = Mock()
        platform.start_game()
        previous = platform.pacer
        previous.note_progress(3)
        platform.start_game()
        self.assertIsNot(platform.pacer, previous)
        self.assertIs(platform.pacer.control, platform.control)
        self.assertEqual(platform.pacer.progress, 0)
        platform.control.start.assert_not_called()

    def test_web_pacing_stop_prevents_browser_input(self):
        platform = WebPlatform.__new__(WebPlatform)
        platform.control = Mock()
        platform.control.wait.side_effect = StopRequested('Time limit')
        platform.driver = Mock()
        platform.pacer = GamePacer(35, 4, platform.control)
        platform._snapshot = {'face': 'facesmile', 'cells': {'1_1': 'square blank'}}
        with self.assertRaises(StopRequested):
            platform._event_batch([(0, 0)])
        platform.driver.execute_script.assert_not_called()

    def test_score_prompt_uses_requested_name(self):
        platform = WebPlatform.__new__(WebPlatform)
        platform.score_name = 'JoshuaBurgenGax'
        platform.driver = Mock()
        alert = platform.driver.switch_to.alert
        alert.text = 'Please enter your name to submit your score (1)'
        self.assertTrue(platform._handle_score_prompt())
        alert.send_keys.assert_called_once_with('JoshuaBurgenGax')
        alert.accept.assert_called_once()
        self.assertTrue(platform.score_prompt_submitted)

    def test_unrelated_prompt_never_receives_score_name(self):
        platform = WebPlatform.__new__(WebPlatform)
        platform.score_name = 'JoshuaBurgenGax'
        platform.driver = Mock()
        platform.driver.switch_to.alert.text = 'Enter your password'
        with self.assertRaisesRegex(RuntimeError, 'Unexpected browser prompt'):
            platform._handle_score_prompt()
        platform.driver.switch_to.alert.send_keys.assert_not_called()
        platform.driver.switch_to.alert.accept.assert_not_called()

    def test_score_submission_is_disabled_without_a_name(self):
        platform = WebPlatform.__new__(WebPlatform)
        platform.score_name = None
        platform.driver = Mock()
        self.assertFalse(platform._handle_score_prompt())
        platform.driver.switch_to.alert.send_keys.assert_not_called()

    def test_score_prompt_does_not_replay_click_batch(self):
        from selenium.common.exceptions import UnexpectedAlertPresentException
        platform = WebPlatform.__new__(WebPlatform)
        platform.score_name = 'JoshuaBurgenGax'
        platform.driver = Mock()
        platform.driver.execute_script.side_effect = UnexpectedAlertPresentException()
        platform.driver.switch_to.alert.text = '1 is a new daily high score! Please enter your name'
        self.assertIsNone(platform._execute_script('click-batch'))
        platform.driver.execute_script.assert_called_once_with('click-batch')
        platform.driver.switch_to.alert.send_keys.assert_called_once_with('JoshuaBurgenGax')

    @patch('Runner.RunControl')
    @patch('Runner.Board')
    @patch('web_platform.WebPlatform')
    def test_retry_restarts_after_loss_and_stops_after_win(self, platform_type, board_type, control_type):
        from Runner import main
        lost, won = Mock(), Mock(won=True)
        lost.play.side_effect = GameLost('Hit a mine.')
        board_type.side_effect = [lost, won]
        self.assertEqual(main(['--platform', 'web', '--retry-on-loss', '--quiet', '--delay', '0']), 0)
        platform_type.return_value.reset.assert_called_once()
        self.assertEqual(board_type.call_count, 2)
        # Setup and total-play clocks only; a loss does not extend the budget.
        self.assertEqual(control_type.call_count, 2)

    @patch('Runner.Board')
    @patch('web_platform.WebPlatform')
    def test_retry_is_off_by_default(self, platform_type, board_type):
        from Runner import main
        board_type.return_value.play.side_effect = GameLost('Hit a mine.')
        self.assertEqual(main(['--platform', 'web', '--delay', '0']), 1)
        platform_type.return_value.reset.assert_not_called()
        self.assertEqual(board_type.call_count, 1)

    @patch('Runner.Board')
    @patch('web_platform.WebPlatform')
    def test_retry_does_not_restart_on_input_errors_or_time_limits(self, platform_type, board_type):
        from Runner import main
        for error, code in [(RuntimeError('Bad input'), 1), (StopRequested('Time limit'), 0)]:
            with self.subTest(error=error):
                board_type.return_value.play.side_effect = error
                self.assertEqual(main(['--platform', 'web', '--retry-on-loss', '--delay', '0']), code)
                platform_type.return_value.reset.assert_not_called()

    def test_reset_discards_old_snapshot_and_checks_fresh_board(self):
        platform = WebPlatform.__new__(WebPlatform)
        platform.control = None
        platform.settle = 0
        platform._rows, platform._cols = 1, 1
        platform.face = Mock()
        platform.driver = Mock()
        platform._By = Mock(ID='id')
        platform.driver.find_element.return_value = platform.face
        platform._snapshot_ready = True
        platform._snapshot = {'face': 'facedead', 'cells': {'1_1': 'square bombdeath'}}
        platform.driver.execute_script.return_value = {
            'face': 'facesmile', 'cells': {'1_1': 'square blank', '0_0': 'square open0'}}
        platform.reset()
        platform.driver.refresh.assert_called_once()
        platform.driver.execute_script.assert_called_once()
        self.assertEqual(platform.read_cell(0, 0), 'square blank')

    def test_reset_waits_for_async_replacement_board(self):
        platform = WebPlatform.__new__(WebPlatform)
        platform.control = Mock()
        platform.settle = 0
        platform._rows, platform._cols = 1, 1
        platform.driver = Mock()
        platform._By = Mock(ID='id')
        platform.driver.execute_script.side_effect = [None, {
            'face': 'facesmile', 'cells': {'1_1': 'square blank'}}]
        platform.reset()
        self.assertEqual(platform.driver.execute_script.call_count, 2)
        platform.control.wait.assert_any_call(0.05)

    def test_victory_prompt_interruption_reads_back_result(self):
        platform = WebPlatform.__new__(WebPlatform)
        platform.control = None
        platform.settle = 0
        platform.input_mode = 'events'
        platform.driver = Mock()
        platform.driver.execute_script.side_effect = [None, {'face': 'facewin', 'cells': {}}]
        platform.reveal_cells([(0, 0)])
        self.assertTrue(platform.game_won())
        self.assertEqual(platform.driver.execute_script.call_count, 2)

    def test_event_batch_returns_snapshot_without_an_extra_read(self):
        platform = WebPlatform.__new__(WebPlatform)
        platform.control = None
        platform.settle = 0
        platform.input_mode = 'events'
        platform.driver = Mock()
        platform.driver.execute_script.return_value = {
            'face': 'facesmile', 'cells': {'1_1': 'square open1', '1_2': 'square open2'}}
        platform.reveal_cells([(0, 0), (0, 1)])
        platform.begin_read()
        self.assertEqual(platform.read_cell(0, 0), 'square open1')
        self.assertEqual(platform.read_cell(0, 1), 'square open2')
        platform.driver.execute_script.assert_called_once()

    def test_event_batches_stop_on_loss(self):
        platform = WebPlatform.__new__(WebPlatform)
        platform.control = None
        platform.settle = 0
        platform.input_mode = 'events'
        platform.driver = Mock()
        platform.driver.execute_script.return_value = {'face': 'facedead', 'cells': {}}
        platform.reveal_cells([(0, c) for c in range(64)])
        platform.driver.execute_script.assert_called_once()

    @patch('Runner.RunControl')
    @patch('Runner.Board')
    @patch('web_platform.WebPlatform')
    def test_web_play_budget_starts_after_browser_setup(self, platform_type, board_type, control_type):
        from Runner import main
        main(['--platform', 'web', '--seconds', '10', '--delay', '0'])
        self.assertEqual([call.args[0] for call in control_type.call_args_list], [60, 10])
        self.assertEqual(platform_type.call_args.kwargs['settle'], 0)

    @patch('builtins.input', return_value='')
    @patch('Runner.Board')
    @patch('web_platform.WebPlatform')
    def test_visible_runner_waits_for_user_before_closing(self, platform_type, board_type, user_input):
        from Runner import main
        self.assertEqual(main(['--platform', 'web', '--show-browser', '--delay', '0']), 0)
        platform_type.assert_called_once()
        self.assertFalse(platform_type.call_args.kwargs['headless'])
        user_input.assert_called_once()
        platform_type.return_value.save_result.assert_called_once()
        platform_type.return_value.close.assert_called_once()

    def test_snapshot_reads_cells_and_confirms_victory(self):
        platform = WebPlatform.__new__(WebPlatform)
        platform.control = None
        platform._snapshot = None
        platform.driver = Mock()
        platform.driver.execute_script.return_value = {
            'face': 'facewin', 'cells': {'1_1': 'square open0'}}
        self.assertEqual(platform.read_cell(0, 0), 'square open0')
        self.assertTrue(platform.game_won())
        platform.driver.execute_script.assert_called_once()

    def test_game_victory_prevents_further_reveal_clicks(self):
        platform = build_platform(2, 2, set())
        platform.revealed.clear()
        # A real game may auto-flag the remaining mines after the last safe click.
        platform.game_won = Mock(return_value=True)
        board = Board(platform, log=False)
        board.reveal_all(set(board.blank))
        self.assertTrue(board.won)
        self.assertEqual(platform.clicks, 1)


import mock
import pytest

from uaclient.api.u.pro.version.v1 import VersionError, VersionResult, _version
from uaclient.exceptions import UserFacingError


class TestVersionV1:
    @mock.patch("uaclient.api.u.pro.version.v1.get_version", return_value="28")
    def test_version(self, _m_get_version, FakeConfig):
        result = _version(cfg=FakeConfig())
        assert isinstance(result, VersionResult)
        assert result.installed_version == "28"

    @mock.patch("uaclient.api.u.pro.version.v1.get_version")
    def test_version_error(self, m_get_version, FakeConfig):
        m_get_version.side_effect = UserFacingError(
            "something wrong", "fn-specific"
        )

        with pytest.raises(VersionError) as excinfo:
            _version(FakeConfig())

        assert excinfo.errisinstance(VersionError)
        assert excinfo.value.msg == "('something wrong', 'fn-specific')"
        assert excinfo.value.msg_code == "unable-to-determine-version"
